"""Application-error → HTTP mapping with the contract error envelope."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ambient_recorder.errors import (
    AssistantNotReadyError,
    ConversationNotFoundError,
    DeviceMissingError,
    DiskLowError,
    SessionNotActiveError,
    SessionNotFoundError,
    SessionStillActiveError,
    SummaryNotFoundError,
    TranscriptionAlreadyRunningError,
    TranscriptionNotReadyError,
    TranscriptNotFinalError,
    TranscriptNotFoundError,
    TurnNotFoundError,
)
from ambient_recorder.logging import jlog
from ambient_recorder.models.api import ErrorBody, ErrorCode, ErrorResponse
from ambient_recorder.storage.protocols import ActiveSessionExistsError


def _envelope(status: int, code: ErrorCode, message: str, detail: dict) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, detail=detail))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DeviceMissingError)
    async def _device_missing(request: Request, exc: DeviceMissingError):
        return _envelope(
            424, ErrorCode.DEVICE_MISSING, str(exc), {"missing": [k.value for k in exc.missing]}
        )

    @app.exception_handler(DiskLowError)
    async def _disk_low(request: Request, exc: DiskLowError):
        return _envelope(
            507,
            ErrorCode.DISK_SPACE_LOW,
            str(exc),
            {"free_mb": exc.free_mb, "required_mb": exc.required_mb},
        )

    @app.exception_handler(ActiveSessionExistsError)
    async def _already_active(request: Request, exc: ActiveSessionExistsError):
        return _envelope(
            409, ErrorCode.SESSION_ALREADY_ACTIVE, str(exc), {"active_session_id": exc.active_id}
        )

    @app.exception_handler(SessionNotFoundError)
    async def _not_found(request: Request, exc: SessionNotFoundError):
        return _envelope(404, ErrorCode.SESSION_NOT_FOUND, str(exc), {"session_id": exc.session_id})

    @app.exception_handler(SessionNotActiveError)
    async def _not_active(request: Request, exc: SessionNotActiveError):
        return _envelope(
            409, ErrorCode.SESSION_NOT_ACTIVE, str(exc), {"session_id": exc.session_id}
        )

    @app.exception_handler(TranscriptNotFoundError)
    async def _transcript_not_found(request: Request, exc: TranscriptNotFoundError):
        return _envelope(404, ErrorCode.TRANSCRIPT_NOT_FOUND, str(exc), {"ref": exc.ref})

    @app.exception_handler(TranscriptionNotReadyError)
    async def _not_ready(request: Request, exc: TranscriptionNotReadyError):
        return _envelope(503, ErrorCode.TRANSCRIPTION_NOT_READY, str(exc), {"reason": exc.reason})

    @app.exception_handler(SessionStillActiveError)
    async def _still_active(request: Request, exc: SessionStillActiveError):
        return _envelope(
            409, ErrorCode.SESSION_STILL_ACTIVE, str(exc), {"session_id": exc.session_id}
        )

    @app.exception_handler(TranscriptionAlreadyRunningError)
    async def _already_running(request: Request, exc: TranscriptionAlreadyRunningError):
        return _envelope(
            409, ErrorCode.TRANSCRIPTION_ALREADY_RUNNING, str(exc), {"session_id": exc.session_id}
        )

    @app.exception_handler(AssistantNotReadyError)
    async def _assistant_not_ready(request: Request, exc: AssistantNotReadyError):
        return _envelope(503, ErrorCode.ASSISTANT_NOT_READY, str(exc), {"reason": exc.reason})

    @app.exception_handler(TranscriptNotFinalError)
    async def _transcript_not_final(request: Request, exc: TranscriptNotFinalError):
        return _envelope(
            409, ErrorCode.TRANSCRIPT_NOT_FINAL, str(exc), {"session_id": exc.session_id}
        )

    @app.exception_handler(SummaryNotFoundError)
    async def _summary_not_found(request: Request, exc: SummaryNotFoundError):
        return _envelope(404, ErrorCode.SUMMARY_NOT_FOUND, str(exc), {"ref": exc.ref})

    @app.exception_handler(ConversationNotFoundError)
    async def _conversation_not_found(request: Request, exc: ConversationNotFoundError):
        return _envelope(404, ErrorCode.CONVERSATION_NOT_FOUND, str(exc), {"cid": exc.cid})

    @app.exception_handler(TurnNotFoundError)
    async def _turn_not_found(request: Request, exc: TurnNotFoundError):
        return _envelope(404, ErrorCode.TURN_NOT_FOUND, str(exc), {"ref": exc.ref})

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return _envelope(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed",
            {"errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception):
        jlog("unhandled_error", error=repr(exc))
        return _envelope(500, ErrorCode.INTERNAL_ERROR, "Internal error", {})
