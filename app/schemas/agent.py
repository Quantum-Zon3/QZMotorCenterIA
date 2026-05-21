from datetime import datetime

from pydantic import BaseModel, Field


class MessageRead(BaseModel):
    id: str
    role: str
    content: str
    model_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationCreate(BaseModel):
    title: str = Field(default="Nueva conversacion", max_length=200)


class ConversationRead(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AgentRunRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    conversation_id: str | None = None
    title: str = Field(default="Nueva conversacion", max_length=200)


class AgentRunResponse(BaseModel):
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    model: str
    response: str
