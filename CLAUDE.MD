以下是你要遵守的基本原则：

1. 整个过程中，你的任何操作请用英文进行思考；对话请保持用中文，这样我的理解会更好一些。
2. 当你执行任务的时候，请调用 Superpower 的 skills。这些 skills 包括：
   (a) Brainstorming
   (b) Write Plan
   (c) Execution
   你可以依次调用这些相关的 skill。
3. 你写程序的时候，请采用 TDD 模式。
4. 注意 Claude 模型的上下文限制：输入输出的 Token 限制.如果你觉得内容可能超过限制，输入时请注意分批次读取大的文档。输出建议建议先创建文档，然后分批次进行输出，防止一次性输出 Token 过大而报如下错误：Claude's response exceeded the 32000 output token maximum. 