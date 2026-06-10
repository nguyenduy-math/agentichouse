"""Pydantic models and enums for the Ticket MCP Server."""

from enum import Enum
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class TicketType(str, Enum):
    leave     = "leave"       # Nghỉ phép
    trip      = "trip"        # Công tác
    overtime  = "overtime"    # Làm thêm giờ
    equipment = "equipment"   # Yêu cầu thiết bị
    training  = "training"    # Đào tạo
    other     = "other"       # Khác


class LeaveType(str, Enum):
    annual    = "annual"      # Nghỉ phép năm
    sick      = "sick"        # Nghỉ ốm
    personal  = "personal"    # Nghỉ việc riêng
    unpaid    = "unpaid"      # Nghỉ không lương
    maternity = "maternity"   # Nghỉ thai sản (nữ)
    paternity = "paternity"   # Nghỉ thai sản (nam)


class TripMode(str, Enum):
    plane = "plane"
    train = "train"
    car   = "car"
    other = "other"


class TicketStatus(str, Enum):
    draft     = "draft"
    pending   = "pending"
    approved  = "approved"
    rejected  = "rejected"
    cancelled = "cancelled"
    completed = "completed"


class TicketPriority(str, Enum):
    low    = "low"
    normal = "normal"
    high   = "high"
    urgent = "urgent"


# Valid status transitions
STATUS_TRANSITIONS: dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.draft:     [TicketStatus.pending, TicketStatus.cancelled],
    TicketStatus.pending:   [TicketStatus.approved, TicketStatus.rejected, TicketStatus.cancelled],
    TicketStatus.approved:  [TicketStatus.completed, TicketStatus.cancelled],
    TicketStatus.rejected:  [TicketStatus.pending, TicketStatus.cancelled],
    TicketStatus.cancelled: [],
    TicketStatus.completed: [],
}


class Ticket(BaseModel):
    ticket_id:       str            = Field(..., description="TKT-YYYYMMDD-NNNN")
    ticket_type:     TicketType
    title:           str
    description:     str            = ""
    requester_name:  str            = Field(..., description="Tên người yêu cầu")
    requester_email: str            = Field(..., description="Email người yêu cầu")
    status:          TicketStatus   = TicketStatus.pending
    priority:        TicketPriority = TicketPriority.normal
    extra_fields:    dict[str, Any] = Field(default_factory=dict,
                                           description="Type-specific fields (JSON)")
    created_at:      datetime
    updated_at:      datetime


class TicketCreate(BaseModel):
    """Input model for generic create_ticket."""
    ticket_type:     TicketType
    title:           str
    description:     str            = ""
    requester_name:  str
    requester_email: str
    priority:        TicketPriority = TicketPriority.normal
    extra_fields:    dict[str, Any] = Field(default_factory=dict)


class TicketUpdate(BaseModel):
    """Input model for update_ticket_status."""
    ticket_id:      str
    new_status:     TicketStatus
    comment:        str = ""
    approver_name:  str = ""
    approver_email: str = ""


class TicketSummary(BaseModel):
    """Lightweight ticket view for list responses."""
    ticket_id:       str
    ticket_type:     TicketType
    title:           str
    requester_name:  str
    requester_email: str
    status:          TicketStatus
    priority:        TicketPriority
    created_at:      datetime


class TicketHistory(BaseModel):
    id:          int
    ticket_id:   str
    action:      str          # "created" | "status_changed" | "comment_added"
    actor_name:  str
    actor_email: str     = ""
    old_value:   str     = ""
    new_value:   str     = ""
    comment:     str     = ""
    timestamp:   datetime
