import asyncio
from fastapi import HTTPException
from llm_config import get_watsonx
from llm_test import ParentingDiaryPipeline

async def run_pipeline_full_test():
    try:
        config = get_watsonx()

        pipeline = ParentingDiaryPipeline()
        
        sample_step1_insight = (
            "아기가 오늘 오후 2시에 거실에서 이유식을 150ml나 혼자서 다 먹어주었다. "
            "너무 대견하고 뿌듯해서 머리를 쓰다듬어 주니 활짝 웃으며 엉뚱한 옹알이를 했다."
        )

        step2_labels = await pipeline.ai_llm_label_model_run_step2(
            step1_insights=sample_step1_insight,
            config=config
        )
        
        if step2_labels.strip():
            print(step2_labels)
        else:
            print("2단계 모델 응답이 비어있습니다. 프롬프트나 설정을 확인하세요.")
            return
        
        final_diary = await pipeline.ai_llm_diary_model_run_step3(
            perfect_match_input=step2_labels,
            config=config
        )
        

        if final_diary.strip():
            print(final_diary)
        else:
            print("3단계 일기 생성이 비어있습니다. 규칙이나 설정을 확인하세요.")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"자동 일기 파이프라인 가동 실패 원인: {str(e)}")


if __name__ == "__main__":
    # 비동기 루프 기동
    asyncio.run(run_pipeline_full_test())
