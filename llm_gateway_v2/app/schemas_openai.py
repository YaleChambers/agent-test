from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OpenAIBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ChatCompletionTextContentPart(OpenAIBaseModel):
    type: Literal["text"]
    text: str


class ChatCompletionImageURL(OpenAIBaseModel):
    url: str
    detail: Literal["auto", "low", "high"] | None = None


class ChatCompletionImageContentPart(OpenAIBaseModel):
    type: Literal["image_url"]
    image_url: ChatCompletionImageURL


class ChatCompletionInputAudio(OpenAIBaseModel):
    data: str
    format: Literal["wav", "mp3"]


class ChatCompletionAudioContentPart(OpenAIBaseModel):
    type: Literal["input_audio"]
    input_audio: ChatCompletionInputAudio


MessageContent = str | list[
    ChatCompletionTextContentPart
    | ChatCompletionImageContentPart
    | ChatCompletionAudioContentPart
]


class ChatCompletionSystemMessageParam(OpenAIBaseModel):
    role: Literal["system"]
    content: MessageContent
    name: str | None = None


class ChatCompletionDeveloperMessageParam(OpenAIBaseModel):
    role: Literal["developer"]
    content: MessageContent
    name: str | None = None


class ChatCompletionUserMessageParam(OpenAIBaseModel):
    role: Literal["user"]
    content: MessageContent
    name: str | None = None


class ChatCompletionFunctionCall(OpenAIBaseModel):
    name: str
    arguments: str


class ChatCompletionFunctionMessageParam(OpenAIBaseModel):
    role: Literal["function"]
    content: str | None
    name: str


class ChatCompletionToolCall(OpenAIBaseModel):
    id: str
    type: Literal["function"]
    function: ChatCompletionFunctionCall


class ChatCompletionAssistantMessageParam(OpenAIBaseModel):
    role: Literal["assistant"]
    content: str | list[ChatCompletionTextContentPart] | None = None
    name: str | None = None
    refusal: str | None = None
    audio: dict[str, Any] | None = None
    tool_calls: list[ChatCompletionToolCall] | None = None
    function_call: ChatCompletionFunctionCall | None = None


class ChatCompletionToolMessageParam(OpenAIBaseModel):
    role: Literal["tool"]
    content: str
    tool_call_id: str


ChatCompletionMessageParam = (
    ChatCompletionSystemMessageParam
    | ChatCompletionDeveloperMessageParam
    | ChatCompletionUserMessageParam
    | ChatCompletionAssistantMessageParam
    | ChatCompletionToolMessageParam
    | ChatCompletionFunctionMessageParam
)


class ChatCompletionFunctionDefinition(OpenAIBaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None
    strict: bool | None = None


class ChatCompletionFunction(OpenAIBaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, Any] | None = None
    strict: bool | None = None


class ChatCompletionTool(OpenAIBaseModel):
    type: Literal["function"]
    function: ChatCompletionFunctionDefinition


class ChatCompletionResponseFormatText(OpenAIBaseModel):
    type: Literal["text"]


class ChatCompletionResponseFormatJSONSchema(OpenAIBaseModel):
    name: str
    description: str | None = None
    schema: dict[str, Any] | None = None
    strict: bool | None = None


class ChatCompletionResponseFormatJSONSchemaParam(OpenAIBaseModel):
    type: Literal["json_schema"]
    json_schema: ChatCompletionResponseFormatJSONSchema


class ChatCompletionResponseFormatJSONObject(OpenAIBaseModel):
    type: Literal["json_object"]


ChatCompletionResponseFormat = (
    ChatCompletionResponseFormatText
    | ChatCompletionResponseFormatJSONSchemaParam
    | ChatCompletionResponseFormatJSONObject
)


class ChatCompletionRequest(OpenAIBaseModel):
    model: str
    messages: list[ChatCompletionMessageParam] = Field(min_length=1)
    audio: dict[str, Any] | None = None
    frequency_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    function_call: Literal["none", "auto"] | ChatCompletionFunctionCall | None = None
    functions: list[ChatCompletionFunction] | None = None
    logit_bias: dict[str, int] | None = None
    logprobs: bool | None = None
    max_completion_tokens: int | None = Field(default=None, gt=0)
    max_tokens: int | None = Field(default=None, gt=0)
    metadata: dict[str, str] | None = None
    modalities: list[Literal["text", "audio"]] | None = None
    n: int | None = Field(default=None, ge=1, le=128)
    parallel_tool_calls: bool | None = None
    prediction: dict[str, Any] | None = None
    presence_penalty: float | None = Field(default=None, ge=-2.0, le=2.0)
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    response_format: ChatCompletionResponseFormat | None = None
    seed: int | None = None
    service_tier: str | None = None
    stop: str | list[str] | None = None
    store: bool | None = None
    stream: bool | None = None
    stream_options: dict[str, Any] | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    tool_choice: Literal["none", "auto", "required"] | dict[str, Any] | None = None
    tools: list[ChatCompletionTool] | None = None
    top_logprobs: int | None = Field(default=None, ge=0, le=20)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    user: str | None = None


class ChatCompletionLogprobToken(OpenAIBaseModel):
    token: str
    logprob: float
    bytes: list[int] | None = None
    top_logprobs: list[dict[str, Any]] | None = None


class ChatCompletionChoiceLogprobs(OpenAIBaseModel):
    content: list[ChatCompletionLogprobToken] | None = None
    refusal: list[ChatCompletionLogprobToken] | None = None


class ChatCompletionMessage(OpenAIBaseModel):
    content: str | None = None
    refusal: str | None = None
    role: Literal["assistant"]
    annotations: list[dict[str, Any]] | None = None
    audio: dict[str, Any] | None = None
    function_call: ChatCompletionFunctionCall | None = None
    tool_calls: list[ChatCompletionToolCall] | None = None


class ChatCompletionChoice(OpenAIBaseModel):
    finish_reason: str | None
    index: int
    message: ChatCompletionMessage
    logprobs: ChatCompletionChoiceLogprobs | None = None


class CompletionTokenDetails(OpenAIBaseModel):
    accepted_prediction_tokens: int | None = None
    audio_tokens: int | None = None
    reasoning_tokens: int | None = None
    rejected_prediction_tokens: int | None = None


class CompletionUsage(OpenAIBaseModel):
    completion_tokens: int
    prompt_tokens: int
    total_tokens: int
    completion_tokens_details: CompletionTokenDetails | None = None
    prompt_tokens_details: dict[str, Any] | None = None


class ChatCompletion(OpenAIBaseModel):
    id: str
    choices: list[ChatCompletionChoice]
    created: int
    model: str
    object: Literal["chat.completion"]
    service_tier: str | None = None
    system_fingerprint: str | None = None
    usage: CompletionUsage | None = None


class OpenAIErrorDetail(OpenAIBaseModel):
    message: str
    type: str
    param: str | None = None
    code: str | None = None


class OpenAIErrorResponse(OpenAIBaseModel):
    error: OpenAIErrorDetail
