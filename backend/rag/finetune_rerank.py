
import numpy as np
from tqdm import tqdm
import os
import logging
import pandas as pd
from torch.utils.data import DataLoader
from sentence_transformers import InputExample, LoggingHandler
from sentence_transformers.cross_encoder import CrossEncoder
from sentence_transformers.evaluation import SentenceEvaluator

class CompanyLawRankingEvaluator(SentenceEvaluator):
    def __init__(self, dev_pairs, name="validation", batch_size=16):
        """
        define a evaluator
        dev_pairs: valid{'query': str, 'positive': str, 'negative': str}
        """
        self.dev_pairs = dev_pairs
        self.name = name
        self.batch_size = batch_size
        self.best_score = -float('inf')
        self.best_epoch = -1

    def __call__(self, model, output_path=None, epoch=-1, steps=-1):

        positive_samples = []
        negative_samples = []

        for pair in self.dev_pairs:
            positive_samples.append(InputExample(texts=[pair['query'], pair['positive']]))
            negative_samples.append(InputExample(texts=[pair['query'], pair['negative']]))

        # input List[List[str]]
        positive_texts = [example.texts for example in positive_samples]
        negative_texts = [example.texts for example in negative_samples]

        positive_scores = model.predict(positive_texts, batch_size=self.batch_size, show_progress_bar=False)
        negative_scores = model.predict(negative_texts, batch_size=self.batch_size, show_progress_bar=False)

        correct = 0
        for i in range(len(positive_scores)):
            if positive_scores[i] > negative_scores[i]:
                correct += 1

        accuracy = correct / len(positive_scores)
        logging.info(
            f"Epoch {epoch} | {self.name} Accuracy: {accuracy:.4f} (Correct: {correct}/{len(positive_scores)})")

        # best_model
        if accuracy > self.best_score:
            self.best_score = accuracy
            self.best_epoch = epoch
            if output_path:
                model.save(os.path.join(output_path, f"best_model_epoch_{epoch}"))
                logging.info(f"Best model saved at epoch {epoch} with accuracy {accuracy:.4f}")

        return accuracy

# log
logging.basicConfig(
    format="%(asctime)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    handlers=[LoggingHandler()]
)

DATA_DIR = "your_data" # give an data example for you,
# {"query": "公司监事会的成员数量要求是什么？", "positive": "公司应当依法设立监事会，监事会的成员不得少于三人。", "negative": "股份有限公司的股东大会应当每年召开一次年会。"}
model_path = "your_rerank_model"
train_batch_size = 8
num_epochs = 5
model_save_path = "save_path" # you can save it in rag/rerank

os.makedirs(model_save_path, exist_ok=True)

model = CrossEncoder(model_path, num_labels=1, max_length=512)


train_df = pd.read_json(os.path.join(DATA_DIR, "rerank_train.jsonl"), lines=True)
val_df = pd.read_json(os.path.join(DATA_DIR, "rerank_val.jsonl"), lines=True)

# construct dataset
train_samples = []
for i, row in train_df.iterrows():
    train_samples.append(InputExample(texts=[row["query"], row["positive"]], label=1))
    train_samples.append(InputExample(texts=[row["query"], row["negative"]], label=0))

# val set
dev_pairs = []
for i, row in val_df.iterrows():
    dev_pairs.append({
        'query': row["query"],
        'positive': row["positive"],
        'negative': row["negative"]
    })


train_dataloader = DataLoader(train_samples, shuffle=True, batch_size=train_batch_size)

evaluator = CompanyLawRankingEvaluator(dev_pairs, name="company-law-eval")

warmup_steps = 100
logging.info(f"Training with warmup steps: {warmup_steps}")


model.fit(
    train_dataloader=train_dataloader,
    evaluator=evaluator,
    epochs=num_epochs,
    evaluation_steps=50,
    optimizer_params={'lr': 1e-5},
    warmup_steps=warmup_steps,
    output_path=model_save_path,
    use_amp=True
)

model.save(model_save_path)
logging.info(f"Model saved to {model_save_path}")