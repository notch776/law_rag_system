from py2neo import Graph, NodeMatcher, Node, Relationship
import numpy as np

graph = Graph("bolt://localhost:7687", auth=("your_name", "your_key"))


def cosine_similarity(vec1, vec2):
    """Calculate the cosine similarity between two vectors"""
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

def handle_insufficient_history(user_query, user_vector,conversation_id):
    # Retrieve the "Company Law Category" node most similar to the user's query vector
    matcher = NodeMatcher(graph)
    company_law_nodes = matcher.match("公司法类别", conversation_id=conversation_id)

    max_similarity = -1
    best_node = None

    for node in company_law_nodes:
        if '向量' in node:
            similarity = cosine_similarity(user_vector, node['向量'])
            if similarity > max_similarity:
                max_similarity = similarity
                best_node = node
                print(best_node)
    if not best_node:
        print("未找到相关的公司法类别节点。")
        return ""

    # Retrieve all "Historical Dialogue" nodes pointed to by the best-matching category node.
    query = """
    MATCH (company_law {name: $company_law_nam, conversation_id: $conversation_id})-[:类型包含]->(history_dialogue:历史对话)
    RETURN history_dialogue
    ORDER BY toInteger(split(history_dialogue.name, '历史对话')[1])
    """
    result = graph.run(query, company_law_name=best_node["name"], conversation_id=conversation_id)

    combined_data = []
    for record in result:
        history_dialogue = record['history_dialogue']

        if '问题向量' not in history_dialogue or history_dialogue['问题向量'] is None:
            continue

        try:
            sim = cosine_similarity(user_vector, history_dialogue['问题向量'])

            if sim > 0.5:
                item = {
                    "问题": history_dialogue.get('问题', ''),
                    "回答": history_dialogue.get('回答', '')
                }
                if sim > 0.8:
                    item["文档"] = history_dialogue.get('文档', '')

                combined_data.append(item)
        except Exception as e:
            print(f"计算历史对话相似度失败: {e}")
            continue

    print("提取的图谱数据:", combined_data)

    lines = []
    for item in combined_data:
        line = f"问题: {item['问题']}"
        if '文档' in item:
            line += f"\n检索到的文档: {item['文档']}"
        line += f"\n回答: {item['回答']}"
        line += f"\n{'-' * 40}"
        lines.append(line)

    combined_text = "\n".join(lines)
    return combined_text


def update_category_vector(category_node):
    """
    Update the vector of the "Company Law Category" node:
    Compute the average of the "question vectors" from all its linked "Historical Dialogue" nodes.
    """
    query = """
    MATCH (c:公司法类别 {name: $name,conversation_id: $conversation_id})-[:类型包含]->(h:历史对话)
    RETURN h.问题向量 AS question_vector
    """
    result = graph.run(query, name=category_node["name"],conversation_id=category_node["conversation_id"]).data()

    vectors = [record["question_vector"] for record in result if record["question_vector"] is not None]
    if vectors:
        # Compute the average vector.
        avg_vector = np.mean(vectors, axis=0).tolist()
        # Update the node's vector.
        category_node["向量"] = avg_vector
        graph.push(category_node)
        print(f"节点 {category_node['name']} 的向量已更新为平均向量。")
    else:
        print(f"节点 {category_node['name']} 无历史对话，未更新向量。")

def save_to_tree(conversation_id, qa_id, info, question_vector, k=5):
    """
    Save the current dialogue into the Neo4j graph.
    Parameters:
        conversation_id: Conversation ID
        qa_id: Current QA turn number
        info: Dictionary containing question, retrieved documents, and answer
        question_vector: Embedding vector of the current question (list[float])
        k: Maximum number of "Company Law Category" nodes allowed
    """
    # Retrieve all existing "Company Law Category" nodes.
    category_nodes = graph.nodes.match("公司法类别", conversation_id=conversation_id).all()
    m = len(category_nodes)  # 当前类别节点数量

    # Current number of category nodes.
    similarities = []
    for node in category_nodes:
        if "向量" in node and node["向量"]:
            sim = cosine_similarity(np.array(question_vector), np.array(node["向量"]))
            similarities.append((sim, node))
        else:
            similarities.append((0.0, node))

    # Determine whether a new category node needs to be created.
    max_sim = max(similarities, key=lambda x: x[0])[0] if similarities else 0.0

    threshold = 0.6
    if max_sim < threshold and m < k:
        # Create a new "Company Law Category" node.
        new_name = f"公司法类别{m + 1}"
        a = Node("公司法类别", name=new_name, 向量=question_vector,conversation_id=conversation_id)
        graph.create(a)
        print(f"创建新类别节点: {new_name}")
    else:
        # Reuse existing category node
        _, a = max(similarities, key=lambda x: x[0])
        print(f"复用现有类别节点: {a['name']} (相似度: {max_sim:.3f})")

    # Create a "Historical Dialogue" node.
    history_name = f"历史对话{qa_id}"
    doc_content = "\n".join(info.get("检索到的文档", [])) if info.get("检索到的文档") else "无"
    answer_text = info.get("回答", "")

    history_node = Node(
        "历史对话",
        name=history_name,
        问题=info.get("问题", ""),
        文档=doc_content,
        回答=answer_text,
        qa_id=qa_id,
        问题向量=question_vector
    )
    graph.create(history_node)

    # relationship: a -[:TYPE_INCLUDES]-> history_node
    rel = Relationship(a, "类型包含", history_node)
    graph.create(rel)
    print(f"创建历史对话节点: {history_name}，并建立关系。")

    # update
    update_category_vector(a)
