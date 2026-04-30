from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.config import settings
from app.core.types import (
    ExamChoice,
    ExamDocument,
    ExamQuestion,
    GenerateExamRequest,
    GraphArtifact,
)
from app.providers.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.services.text_utils import normalize_text
from app.storage.local import load_exam, load_graph_artifact, load_session, save_exam

EXAM_DETAILED_CONCEPT_LIMIT = 56
EXAM_MAX_EDGE_LINES = 120

EXAM_SYSTEM_PROMPT = """\
你是课程图谱出卷器。你会读取当前课程的知识图谱 JSON，并生成一份可直接用于课堂测验的结构化试卷。

要求：
- 只基于当前课程图谱出题，不接入 Web Search，不使用外部资料。
- 题目要覆盖核心知识点、桥梁知识点、前置知识点和易混淆关系。
- 每题必须有答案和解析，解析要能帮助学生复习。
- 输出必须是 JSON object，不要 Markdown、来源、页码、引用、chunk_id。
"""

EXAM_STYLE_RULES = """\
出卷规则：
- 试卷只基于当前课程图谱，不接入 Web Search，不使用外部资料。
- 优先覆盖高 importance_score 概念，确保核心知识点被考到。
- 高 betweenness_centrality 概念用于综合题，考察跨模块连接。
- 高 prerequisite_score 概念用于基础题，考察前置理解；如果图谱暂未提供该指标，就用 prerequisites 和关系类型 prerequisite_of 推断。
- 高 relation_diversity_score 概念用于辨析题，考察相似概念、操作语义、约束区别；如果图谱暂未提供该指标，就用该概念参与的关系类型数量推断。
- 题目覆盖比例默认：70% 高重要度概念，20% 桥梁/前置概念，10% 易混淆或关系密集概念。
- 每题必须包含题干、题型、答案、解析、难度、关联概念和考察点。
- question_type 只能从本次“允许题型”中选择，可用值为 single_choice / multiple_choice / true_false / fill_blank / short_answer / essay。
- 选择题干扰项应来自相近概念或常见混淆，不随机编造。
- 单选题和多选题必须提供 4 个选项，choice_id 使用 A/B/C/D。
- 判断题必须提供答案“正确”或“错误”。
- 填空题答案必须给出可精确判定的标准答案；如果有多个等价答案，用“；”分隔。
- 简答题答案要简洁，但解析要说明评分点。
- 论述题应考察跨概念综合理解，答案给出分点要点，解析说明评分维度。
- 数据库/系统/网络课优先考机制、流程、语义、约束、操作区别和典型场景。
- 数学/统计/机器学习课可考定义、公式、变量含义、推导关系和应用条件。
- 不为了形式强行出公式题；只有图谱内容包含数学结论时才出公式相关题。
- 输出必须是 JSON object，不要 Markdown、来源、页码、引用、chunk_id。
"""


class LLMExamChoice(BaseModel):
    choice_id: str
    text: str


class LLMExamQuestion(BaseModel):
    question_type: str
    stem: str
    choices: list[LLMExamChoice] = Field(default_factory=list)
    answer: str
    explanation: str
    difficulty: str = "medium"
    concept_ids: list[str] = Field(default_factory=list)
    tested_points: list[str] = Field(default_factory=list)
    importance_basis: str = ""


class LLMExamDocument(BaseModel):
    title: str = ""
    summary: str = ""
    questions: list[LLMExamQuestion] = Field(default_factory=list)


def generate_exam(request: GenerateExamRequest) -> ExamDocument:
    graph = load_graph_artifact(request.session_id)
    session = load_session(request.session_id)
    if not graph.concepts:
        raise ValueError("No concepts available to generate exam.")

    llm_exam = _generate_exam_with_llm(
        graph,
        lecture_title=session.lecture_title,
        question_count=request.question_count,
        question_types=request.question_types,
    )
    valid_concept_ids = {concept.concept_id for concept in graph.concepts}
    questions: list[ExamQuestion] = []
    for question in llm_exam.questions:
        stem = normalize_text(question.stem)
        answer = normalize_text(question.answer)
        explanation = normalize_text(question.explanation)
        if not stem or not answer or not explanation:
            continue
        allowed_types = _normalize_question_types(request.question_types)
        question_type = _normalize_question_type(question.question_type)
        if question_type not in allowed_types:
            continue
        concept_ids = [concept_id for concept_id in question.concept_ids if concept_id in valid_concept_ids]
        if not concept_ids:
            continue
        choices = [
            ExamChoice(choice_id=normalize_text(choice.choice_id).upper(), text=normalize_text(choice.text))
            for choice in question.choices
            if normalize_text(choice.choice_id) and normalize_text(choice.text)
        ]
        if question_type in {"single_choice", "multiple_choice"} and len(choices) < 4:
            continue
        if question_type in {"single_choice", "multiple_choice"}:
            choices = choices[:4]
        questions.append(
            ExamQuestion(
                question_type=question_type,
                stem=stem,
                choices=choices,
                answer=answer,
                explanation=explanation,
                difficulty=_normalize_difficulty(question.difficulty),
                concept_ids=concept_ids,
                tested_points=[normalize_text(point) for point in question.tested_points if normalize_text(point)],
                importance_basis=normalize_text(question.importance_basis),
            )
        )

    if not questions:
        raise ValueError("Exam LLM returned no usable questions.")

    exam = ExamDocument(
        session_id=request.session_id,
        title=normalize_text(llm_exam.title) or f"{session.lecture_title} - 图谱试卷",
        summary=normalize_text(llm_exam.summary) or f"基于当前图数据库生成 {len(questions)} 道题。",
        questions=questions[: request.question_count],
    )
    save_exam(exam)
    return exam


def get_exam(session_id: uuid.UUID) -> ExamDocument:
    return load_exam(session_id)


def _generate_exam_with_llm(
    graph: GraphArtifact,
    *,
    lecture_title: str,
    question_count: int,
    question_types: list[str] | None = None,
) -> LLMExamDocument:
    if not settings.exam_llm_api_key or not settings.exam_llm_model:
        raise RuntimeError("Exam LLM is not configured. Set EXAM_LLM_API_KEY and EXAM_LLM_MODEL.")

    provider = OpenAICompatibleLLMProvider(
        api_key=settings.exam_llm_api_key,
        base_url=settings.exam_llm_base_url,
        model=settings.exam_llm_model,
        timeout_seconds=settings.exam_llm_timeout_seconds,
        max_output_tokens=settings.exam_llm_max_output_tokens,
    )
    payload = provider.generate_json(
        prompt=_build_exam_prompt(
            graph,
            lecture_title=lecture_title,
            question_count=question_count,
            question_types=question_types,
        ),
        system=EXAM_SYSTEM_PROMPT,
        temperature=0.25,
        max_output_tokens=settings.exam_llm_max_output_tokens,
    )
    return LLMExamDocument.model_validate(payload)


def _build_exam_prompt(
    graph: GraphArtifact,
    *,
    lecture_title: str,
    question_count: int,
    question_types: list[str] | None = None,
) -> str:
    concept_by_id = {concept.concept_id: concept for concept in graph.concepts}
    sorted_concepts = sorted(graph.concepts, key=lambda item: item.importance_score, reverse=True)
    detailed_concepts = sorted_concepts[:EXAM_DETAILED_CONCEPT_LIMIT]
    detailed_ids = {concept.concept_id for concept in detailed_concepts}
    allowed_types = _normalize_question_types(question_types or [])
    lines = [
        f"课程讲次：{lecture_title}",
        f"题目数量：{question_count}",
        f"允许题型：{', '.join(allowed_types)}",
        f"出卷 API base_url：{settings.exam_llm_base_url}",
        f"出卷模型配置目标：{settings.exam_llm_model}",
        "",
        EXAM_STYLE_RULES.strip(),
        "",
        "请输出 JSON：",
        '{"title":"","summary":"","questions":[{"question_type":"single_choice","stem":"","choices":[{"choice_id":"A","text":""},{"choice_id":"B","text":""},{"choice_id":"C","text":""},{"choice_id":"D","text":""}],"answer":"","explanation":"","difficulty":"medium","concept_ids":["concept:id"],"tested_points":[""],"importance_basis":""}]}',
        "",
        "图谱聚类：",
    ]

    for cluster in graph.topic_clusters:
        concept_names = [
            concept_by_id[concept_id].name
            for concept_id in cluster.concept_ids
            if concept_id in concept_by_id
        ]
        lines.append(f"- {cluster.cluster_id} {cluster.title}: {'、'.join(concept_names)}")

    lines.extend(["", "高优先级概念："])
    for concept in detailed_concepts:
        parts = [
            f"id={concept.concept_id}",
            f"name={concept.name}",
            f"canonical={concept.canonical_name}",
            f"importance_score={concept.importance_score:.4f}",
        ]
        if concept.graph_metrics:
            parts.append(
                "graph_metrics="
                + "，".join(f"{key}={value:.4f}" for key, value in sorted(concept.graph_metrics.items()))
            )
        if concept.definition:
            parts.append(f"definition={concept.definition[:180]}")
        if concept.summary:
            parts.append(f"summary={concept.summary[:220]}")
        if concept.key_points:
            parts.append(f"key_points={'；'.join(concept.key_points[:4])}")
        if concept.prerequisites:
            parts.append(f"prerequisites={'、'.join(concept.prerequisites[:4])}")
        if concept.applications:
            parts.append(f"applications={'、'.join(concept.applications[:4])}")
        lines.append("- " + " | ".join(parts))

    remaining_concepts = [concept for concept in sorted_concepts if concept.concept_id not in detailed_ids]
    if remaining_concepts:
        lines.extend(["", "其余概念目录："])
        for concept in remaining_concepts:
            parts = [
                f"id={concept.concept_id}",
                f"name={concept.name}",
                f"importance_score={concept.importance_score:.4f}",
            ]
            if concept.definition:
                parts.append(f"definition={concept.definition[:80]}")
            lines.append("- " + " | ".join(parts))

    lines.extend(["", "关系边（用于设计综合题、辨析题和干扰项）："])
    ranked_edges = sorted(
        graph.edges,
        key=lambda edge: (
            concept_by_id.get(edge.source).importance_score if concept_by_id.get(edge.source) else 0.0
        )
        + (
            concept_by_id.get(edge.target).importance_score if concept_by_id.get(edge.target) else 0.0
        ),
        reverse=True,
    )
    for edge in ranked_edges[:EXAM_MAX_EDGE_LINES]:
        source = concept_by_id.get(edge.source)
        target = concept_by_id.get(edge.target)
        if source is None or target is None:
            continue
        relation_type = edge.properties.get("relation_type") or edge.edge_type
        lines.append(f"- {source.name} -> {target.name} ({relation_type})")
    if len(graph.edges) > EXAM_MAX_EDGE_LINES:
        lines.append(f"- 其余 {len(graph.edges) - EXAM_MAX_EDGE_LINES} 条低优先级关系可作为背景，不必逐条使用。")

    lines.extend(
        [
            "",
            "生成要求：",
            f"- 生成恰好 {question_count} 道题。",
            f"- 只生成允许题型中的题目：{', '.join(allowed_types)}。",
            "- 所选题型都应尽量覆盖；如果课程内容不适合某题型，可以减少该题型。",
            "- concept_ids 必须使用上面给出的 concept:id。",
            "- importance_basis 用一句话说明为什么这道题重要，例如“高 importance_score + 连接多个查询谓词”。",
        ]
    )
    return "\n".join(lines)


def _normalize_question_type(value: str) -> str:
    normalized = normalize_text(value).lower()
    aliases = {
        "single": "single_choice",
        "single_choice": "single_choice",
        "choice": "single_choice",
        "单选": "single_choice",
        "multiple": "multiple_choice",
        "multiple_choice": "multiple_choice",
        "多选": "multiple_choice",
        "true_false": "true_false",
        "判断": "true_false",
        "判断题": "true_false",
        "fill": "fill_blank",
        "fill_blank": "fill_blank",
        "blank": "fill_blank",
        "填空": "fill_blank",
        "填空题": "fill_blank",
        "short": "short_answer",
        "short_answer": "short_answer",
        "简答": "short_answer",
        "简答题": "short_answer",
        "essay": "essay",
        "论述": "essay",
        "论述题": "essay",
    }
    return aliases.get(normalized, "short_answer")


def _normalize_question_types(values: list[str]) -> list[str]:
    types = [_normalize_question_type(value) for value in values]
    deduped = list(dict.fromkeys(types))
    if deduped:
        return deduped
    return ["single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"]


def _normalize_difficulty(value: str) -> str:
    normalized = normalize_text(value).lower()
    if normalized in {"easy", "简单", "low"}:
        return "easy"
    if normalized in {"hard", "困难", "高"}:
        return "hard"
    return "medium"
