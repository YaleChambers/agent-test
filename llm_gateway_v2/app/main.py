from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .core.errors import GatewayError
from .api.routes import router


app = FastAPI(title="Minimal LLM Gateway")
app.include_router(router)


@app.exception_handler(GatewayError)
async def gateway_error_handler(request: Request, exc: GatewayError):
	return JSONResponse(
		status_code=exc.status_code,
		content={"detail": {"code": exc.code, "message": exc.message}},
	)
