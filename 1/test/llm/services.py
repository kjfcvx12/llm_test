from typing import Dict, Any
from llm import WatsonxDiaryGenerator
from app.db.models.logs import Log



class ParentingDiaryService:
    async def process_auto_diary_generation(self, log_record: Log) -> Dict[str, Any]:

        ai_engine = await WatsonxDiaryGenerator()
        # 분리 작성된 독립형 AI 모델 엔진 비동기 일괄 작동
        ai_outputs = await ai_engine.execute_async_pipeline(log_record.l_content)
        
        # diaries 테이블의 규격에 어울리도록 딕셔너리 구조 빌드
        diary_payload = {
            "d_title": f"{log_record.l_date.strftime('%Y년 %m월 %d일')} 자동 생성 일기",
            "d_content": ai_outputs["final_diary"],
            "d_label": ai_outputs["db_categories"]["d_label"],
            "d_eat": ai_outputs["db_categories"]["d_eat"],
            "d_sleep": ai_outputs["db_categories"]["d_sleep"],
            "d_toilet": ai_outputs["db_categories"]["d_toilet"],
            "d_temp": ai_outputs["db_categories"]["d_temp"],
            "b_id": log_record.b_id,
        }
        
        return diary_payload