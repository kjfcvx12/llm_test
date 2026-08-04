from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db

from app.schemas.diaries import DiaryPipelineRequest, DiaryPipelineResponse
from app.crud.diaries import get_log_by_id_async, create_diary_record_async
from app.services.diaries import ParentingDiaryService

router = APIRouter(prefix="/api/v1/diaries", tags=["Auto Diary System"])
service_layer = ParentingDiaryService()

@router.post("/generate", response_model=DiaryPipelineResponse)
async def generate_parenting_diary_api(
    payload: DiaryPipelineRequest, 
    db: AsyncSession = Depends(get_db)
):
    # 1. DB에서 특정 메모 ID(l_id) 정보 로드
    log_record = await get_log_by_id_async(db, payload.l_id)
    if not log_record:
        raise HTTPException(status_code=404, detail="요청하신 로그 식별자를 DB에서 찾을 수 없습니다.")

    try:
        # 2. 서비스 레이어(내부의 독립형 AI 모델 엔진)를 통한 자동 일기 작성 파이프라인 가동
        diary_payload = await service_layer.process_auto_diary_generation(log_record)
        
        # 3. 작성 완료된 데이터를 diaries 테이블에 비동기 영속화(Insert)
        created_diary = await create_diary_record_async(db, diary_payload)

        return DiaryPipelineResponse(
            success=True,
            l_id=log_record.l_id,
            b_id=log_record.b_id,
            created_d_id=created_diary.d_id,
            step1_preprocessed=diary_payload["step1_insights"],
            step2_labels_raw=diary_payload["step2_keywords"],
            final_diary_content=diary_payload["d_content"]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"자동 일기 파이프라인 가동 실패 원인: {str(e)}")
