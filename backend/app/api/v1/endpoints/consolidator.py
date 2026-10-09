"""Endpoints REST para processar projetos e baixar os arquivos dos jobs."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.schemas.consolidator import (
	ConsolidateLocalRequest,
	ConsolidateUploadRequest,
	ConsolidationJobResponse,
	ProfileConfig,
)
from app.services.consolidator_service import ConsolidatorService, ConsolidatorServiceError


router = APIRouter(prefix="/consolidator", tags=["Consolidator"])
_service = ConsolidatorService()
_MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024


def get_consolidator_service() -> ConsolidatorService:
	"""Fornece o servico compartilhado; pode ser sobrescrito em testes."""
	return _service


@router.post("/process-local", response_model=ConsolidationJobResponse)
async def process_local(
	request: ConsolidateLocalRequest,
	service: Annotated[ConsolidatorService, Depends(get_consolidator_service)],
) -> ConsolidationJobResponse:
	"""Consolida um diretorio local acessivel pelo servidor."""
	try:
		return await run_in_threadpool(service.process_local, request)
	except ConsolidatorServiceError as error:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/process-upload", response_model=ConsolidationJobResponse)
async def process_upload(
	file: Annotated[UploadFile, File(description="Arquivo ZIP do projeto")],
	config: Annotated[str, Form(description="Configuracao de perfil em JSON")],
	service: Annotated[ConsolidatorService, Depends(get_consolidator_service)],
) -> ConsolidationJobResponse:
	"""Recebe um ZIP e uma configuracao JSON e cria um job de consolidacao."""
	filename = file.filename or ""
	if Path(filename).suffix.casefold() != ".zip":
		raise HTTPException(
			status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
			detail="O arquivo enviado deve ter extensao .zip",
		)

	try:
		request = _parse_upload_config(config)
	except (json.JSONDecodeError, ValidationError, ValueError) as error:
		detail = error.errors() if isinstance(error, ValidationError) else str(error)
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from error

	try:
		zip_bytes = await file.read(_MAX_UPLOAD_SIZE_BYTES + 1)
		if len(zip_bytes) > _MAX_UPLOAD_SIZE_BYTES:
			raise HTTPException(
				status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
				detail="O ZIP excede o limite de 100 MB",
			)
		if not zipfile.is_zipfile(BytesIO(zip_bytes)):
			raise HTTPException(
				status_code=status.HTTP_400_BAD_REQUEST,
				detail="O conteudo enviado nao e um arquivo ZIP valido",
			)
		return await run_in_threadpool(service.process_upload, zip_bytes, request)
	except ConsolidatorServiceError as error:
		raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
	finally:
		await file.close()


@router.get("/download/{job_id}/{file_type}")
async def download_job_file(
	job_id: str,
	file_type: str,
	service: Annotated[ConsolidatorService, Depends(get_consolidator_service)],
) -> FileResponse:
	"""Transmite o TXT consolidado ou o log de exclusoes de um job."""
	try:
		file_path = service.get_job_file(job_id, file_type)  # type: ignore[arg-type]
	except ValueError as error:
		raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
	except FileNotFoundError as error:
		raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job ou arquivo nao encontrado") from error

	filename = "consolidated.txt" if file_type == "consolidated" else "exclusions.log"
	return FileResponse(file_path, media_type="text/plain; charset=utf-8", filename=filename)


@router.get("/profiles", response_model=dict[str, ProfileConfig])
async def get_profiles() -> dict[str, dict[str, list[str] | None]]:
	"""Lista os perfis predefinidos disponiveis para consolidacao."""
	return ConsolidatorService.list_profiles()


def _parse_upload_config(raw_config: str) -> ConsolidateUploadRequest:
	"""Valida configuracao JSON, aceitando DTO de upload ou ProfileConfig direto."""
	data = json.loads(raw_config)
	if not isinstance(data, dict):
		raise ValueError("A configuracao JSON deve ser um objeto")

	profile_fields = {
		"extensions",
		"subfolders",
		"excluded_dirs",
		"custom_sensitive_patterns",
	}
	if profile_fields.intersection(data):
		profile_config_data = {key: data[key] for key in profile_fields if key in data}
		profile_config = ProfileConfig.model_validate(profile_config_data)
		request_data = {key: value for key, value in data.items() if key not in profile_fields}
		request_data.setdefault("profile", "custom")
		request_data["custom_rules"] = profile_config
		return ConsolidateUploadRequest.model_validate(request_data)

	return ConsolidateUploadRequest.model_validate(data)