# RAG 产品成熟化设计

更新时间：2026-06-06

本项目不只按课题 PDF 的最小链路推进，而是参考成熟 RAG / Agent 系统的共性做法，逐步把 Demo 改造成可持续扩展的产品架构。

## 外部参考

- RAG 原始论文：RAG 的核心价值是把参数化模型和外部非参数化知识库结合，降低只靠模型参数回答带来的事实性问题。参考：https://arxiv.org/abs/2005.11401
- Self-RAG：成熟 RAG 不应无条件固定检索，而应判断是否需要检索、检索是否有用，并对生成结果做自我检查。参考：https://arxiv.org/abs/2310.11511
- LangGraph：成熟 Agent 应有明确的状态、节点、工具和可观测工作流，而不是把所有逻辑塞进一个函数。参考：https://docs.langchain.com/oss/python/langgraph/overview
- LlamaIndex Query Transformations：复杂用户问题需要查询改写、分解或转换，再进入检索。参考：https://developers.llamaindex.ai/python/framework/optimizing/advanced_retrieval/query_transformations/
- OpenAI Structured Outputs：让模型输出符合 JSON Schema 的结构化结果，比让模型直接自由决定业务动作更可靠。参考：https://platform.openai.com/docs/guides/structured-outputs
- RAGAS：成熟 RAG 需要可评估指标，例如 faithfulness、answer relevancy、context precision/recall 等。参考：https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/

## 本项目采用的原则

1. **语义理解结构化**
   - 用户自然语言先进入 `SemanticPlanner`。
   - 默认走快速规则 fallback，保证演示延迟稳定。
   - 如果 `USE_SEMANTIC_LLM=true` 且 LLM 可用，再让模型输出结构化 JSON plan。
   - 后端用 Pydantic schema 校验 plan，失败时回退规则解析。
   - 模型只负责理解意图，不直接修改购物车、不直接编商品事实。

2. **工具执行可控**
   - `AgentWorkflow` 根据 plan 选择 handler。
   - `ToolRegistry` 执行检索、对比、购物车等真实动作。
   - 商品 ID、价格、品牌、详情页和购物车状态都来自后端数据，不由模型自由生成。

3. **上下文引用泛化**
   - 支持序号引用：`第二个怎么样`、`第2款`。
   - 支持品牌/名称引用：`AHC 那个`、`科颜氏先不要了`。
   - 支持自然指代：`那支给我来两件`、`便宜的那个`。
   - 支持参考商品继续检索：`有没有比第二款更适合敏感肌但别太贵的`。

4. **检索前查询增强**
   - 宽泛需求先澄清。
   - 澄清后的下一轮会补回 pending subject。
   - 多轮上下文会转换成明确过滤条件，如 max_price、keyword、exclude。

5. **Grounded 生成**
   - LLM 只基于候选商品生成回答。
   - 检索为空时明确降级，不返回虚假商品卡。
   - 商品卡和对比卡始终以结构化 SSE 发送给 Android。

6. **可评估可回归**
   - 每次能力增强都加入 pytest 场景。
   - 当前测试覆盖澄清、对比、购物车、上下文追问、语义 planner、LLM fallback 和 API SSE。
   - 下一阶段应增加一组离线 benchmark，按 RAGAS 风格记录命中率、相关性和事实一致性。

## 当前已落地

```text
Android App
  -> /chat SSE
  -> Orchestrator
  -> SemanticPlanner
     -> LLM JSON plan 或规则 fallback
     -> Pydantic 校验
  -> AgentWorkflow
     -> ClarificationHandler
     -> CartHandler
     -> CompareHandler
     -> ContextFollowUpHandler
     -> RecommendationHandler
  -> ToolRegistry
  -> Search / Compare / Cart
  -> Grounded response + structured SSE events
```

## 下一阶段产品化路线

1. **Retrieval Quality**
   - 真实 embedding 灌库回归。
   - 加入 rerank 层，解决 Top-K 只靠初始召回的问题。
   - 针对类目、品牌、价格、功效词做混合检索。

2. **Planner Quality**
   - 为 `SemanticPlanner` 增加 few-shot 示例。
   - 记录 plan、工具调用、检索结果和最终回答，方便定位错误。
   - 对低置信度 plan 主动澄清，而不是强行执行。

3. **Evaluation**
   - 建立 `data/eval_queries.jsonl`。
   - 每条样例标注期望意图、期望商品、过滤条件和是否应澄清。
   - 增加离线评估脚本，输出 query success rate、cart action accuracy、grounding consistency。

4. **Product Experience**
   - 增加商品详情页更完整信息。
   - 购物车支持清空、继续推荐搭配商品。
   - Android 端展示“当前理解到的条件”，让用户可修改。

5. **Multimodal**
   - 接入图片输入后，先输出结构化视觉摘要，再进入同一个 `SemanticPlanner`。
   - 图片理解结果仍不能直接生成商品事实，必须通过商品库检索验证。
