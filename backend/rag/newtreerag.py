import requests
import json
from dotenv import load_dotenv
import os
from openai import OpenAI
import redis
import threading
from rag.neotree import save_to_tree, handle_insufficient_history
from rag import rengong
from rag.search_similar import search_similar

load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

client = OpenAI(
    api_key=DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True)

def call_qianwen_max(prompt):
    """Qwen-Max"""
    try:
        response = client.chat.completions.create(
            model="qwen-max",
            messages=[
                {"role": "system",
                 "content": "你是一名企业法律专家。请根据提供的上下文判断是否能充分回答用户问题。\n"
                            "请严格按以下格式返回：\n"
                            "是否足够: 1\n"
                            "回答: <你的回答>\n\n"
                            "如果信息不足，请返回：\n"
                            "是否足够: 0\n"
                            "回答: <尝试回答或说明信息不足>"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1024
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"调用大模型时出错: {e}")
        return "是否足够: 0\n回答: 调用模型失败，无法回答。"


def extract_enough_flag_and_answer(model_output):
    """extract the 'IsEnough' flag"""
    lines = model_output.strip().split('\n')
    enough_flag = 0
    answer = ""

    for line in lines:
        if line.startswith("是否足够:"):
            try:
                enough_flag = int(line.split(":")[1].strip())
            except:
                enough_flag = 0
        elif line.startswith("回答:"):
            answer = line.split(":", 1)[1].strip()

    return enough_flag, answer


import json


def get_all_history_from_redis(conversation_id):
    """conversation_id from Redis."""
    history_list = []
    pattern = f"对话{conversation_id}*"

    try:
        for key in r.scan_iter(match=pattern, count=100):
            data = r.get(key)
            if data:
                try:
                    info = json.loads(data)
                    history_list.append(info)
                except json.JSONDecodeError as e:
                    print(f"解析 JSON 失败，key={key}: {e}")
    except Exception as e:
        print(f"扫描 Redis key 失败: {e}")

    return history_list


def rag_company_law_qa(query, conversation_id):
    #use search_similar
    similar_docs_result, user_vector = search_similar(query)
    detector = rengong.HumanHandoffDetector()
    if detector.need_human(query):
        # handoff-to-human indicator
        return "正在为您转接人工客服，请稍候...", 2, None
    context = ""
    if similar_docs_result and len(similar_docs_result) > 0:
        context = "\n".join([
            f"【来源】《{doc['filename']}》，相关条文（相似度: {doc['score']:.3f}）:\n{doc['content']}"
            for doc in similar_docs_result
        ])
    else:
        context = "未检索到相关法律条文。"

    # Retrieve historical dialogues from Redis
    history_data = get_all_history_from_redis(conversation_id)
    history_context = ""
    for item in history_data:
        history_context += f"问题: {item.get('问题', '')}\n"
        history_context += f"回答: {item.get('回答', '')}\n"
        history_context += "-" * 40 + "\n"

    # prompt
    full_prompt = f"""
你是一名企业法律专家。请根据以下信息回答用户问题：

【历史对话】
{history_context if history_context.strip() else '无历史对话'}

【检索到的相关法律条文】
{context}

【当前用户问题】
{query}
这里给出的历史对话不是全部，你还可以请求到更早的历史信息，如果你认为历史数据不够，可以继续请求。
请严格按以下格式返回：
是否足够: 1
回答: <你的回答>

如果信息不足，请返回：
是否足够: 0
回答: <尝试回答或说明信息不足>
"""


    model_response = call_qianwen_max(full_prompt)
    enough_flag, final_answer = extract_enough_flag_and_answer(model_response)
    if enough_flag == 0:
        additional_context = handle_insufficient_history(query, user_vector,conversation_id)
        full_prompt += (f"\n附加相关历史对话上下文:\n{additional_context}\n本次返回只能以下格式返回:"
                        f"是否足够: 1"
                        f"回答: <你的回答>")

        print(full_prompt)
        model_response = call_qianwen_max(full_prompt)
        enough_flag, final_answer = extract_enough_flag_and_answer(model_response)
    return final_answer, enough_flag, user_vector


def store_in_redis(conversation_id, qa_id, info, user_vector, k=5):
    """Save to Redis and asynchronously sync to Neo4j"""
    key = f"对话{conversation_id}历史信息{qa_id}"
    r.set(key, json.dumps(info), ex=100)

    # Start an asynchronous task to save to the graph
    timer = threading.Timer(30.0, save_to_tree, args=[conversation_id, qa_id, info, user_vector, k])
    timer.start()



#just test demo~~
if __name__ == "__main__":
    user_id = input("请输入您的用户ID: ").strip()
    try:
        user_id = int(user_id)
    except:
        user_id = hash(user_id)

    n = 1
    while True:
        user_query = input("> ").strip()
        if user_query.lower() == 'exit':
            break
        if not user_query:
            continue
        detector = HumanHandoffDetector()
        if detector.need_human(user_query):
            print("触发转人工")
        else:
            print("机器人继续处理")
            # RAG
            result, enough_flag, user_vector = rag_company_law_qa(user_query, user_id)

            print("\n回答：")
            print(result)
            print(f"\n是否信息足够: {'是' if enough_flag else '否'}")
            print("\n" + "-" * 60 + "\n")


            similar_docs_result, _ = search_similar(user_query)
            retrieved_docs = [doc['content'] for doc in similar_docs_result] if similar_docs_result else []

            info = {
                "问题": user_query,
                "检索到的文档": retrieved_docs,
                "回答": result
            }

            # save
            store_in_redis(user_id, n, info, user_vector)
            n += 1