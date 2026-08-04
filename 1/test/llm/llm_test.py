from fastapi import HTTPException
from langchain_ibm import ChatWatsonx
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


class ParentingDiaryPipeline:
    def __init__(self):
        self.ai_llm_label_model = None
        self.ai_llm_diary_model = None


    def get_ai_llm_label_model(self, config: dict) -> ChatWatsonx:
        if self.ai_llm_label_model is None:
            extract_params = {
                "decoding_method": "greedy",
                "min_new_tokens": 10,
                "max_new_tokens": 500,
                "repetition_penalty": 1.0,
            }
            
            self.ai_llm_label_model = ChatWatsonx(
                model_id="mistralai/mistral-small-3-1-24b-instruct-2503",
                url=config["credentials"]["url"],
                apikey=config["credentials"]["apikey"],
                project_id=config["project_id"],
                params=extract_params
            )
        return self.ai_llm_label_model
    

    def get_ai_llm_diary_model(self, config: dict) -> ChatWatsonx:
        if self.ai_llm_diary_model is None:
            creative_params = {
                "decoding_method": "sample",
                "min_new_tokens": 45,
                "max_new_tokens": 400,
                "repetition_penalty": 1.05,
                "temperature": 0.2,
                "top_p": 0.8,
                "stop_sequences": ["\n\n", "[END]"]
            }
            
            self.ai_llm_diary_model = ChatWatsonx(
                model_id="meta-llama/llama-3-3-70b-instruct",
                url=config["credentials"]["url"],
                apikey=config["credentials"]["apikey"],
                project_id=config["project_id"],
                params=creative_params
            )
        return self.ai_llm_diary_model


    async def ai_llm_label_model_run_step2(self, step1_insights: str, config: dict) -> str:

        prompt = ChatPromptTemplate.from_template("""[Instruction]
                                                  당신은 육아 기록 전문가입니다.
                                                  주어진 [Data]의 각 문장을 순서대로 정밀 분석하여 아래 [Output Format] 양식에 맞춰 오직 핵심 라벨 결과만 깨끗하게 출력하세요.

                                                  [추출 규칙]
                                                  1. 문장원문 항목에는 주어진 [Data]의 문장을 글자, 띄어쓰기, 문장 부호까지 있는 그대로 복사하여 붙여넣기하세요.
                                                  2. 모든 출력 결과는 오직 '한국어'만 사용하세요.
                                                  3. 원문 자체에 한국어 외의 글자가 직접 적혀 있는 경우에만 해당 글자를 변형 없이 그대로 결과에 포함하여 출력하세요. 
                                                  4. [Output Format]의 8개 항목은 모든 문장마다 무조건 전부 화면에 나타나야 하고 원문에 내용이 없거나 추출할 수 없는 항목은 '없음'이라는 두 글자를 채워서 출력하세요.
                                                  5. 문맥을 파악하여 행동을 행한 주체(예: 아기, 엄마 등)가 누구인지 명확히 인지하고 추출을 진행하세요.

                                                  [카테고리 규칙]
                                                  - 핵심어
                                                  주체(누가)·행동(무엇을 하다)·대상(무엇을)·장소(어디서)·시간(언제)·이유(왜)·상태(어떠한가)·방식(어떻게)·결과(어떻게 되다)·수치(얼마나)·상대(누구와)·감정(어떤 기분으로)·대책(어떻게 대처했나)
                                                  이 중에서 문장에 존재하는 것들을 명사 혹은 서술어로 출력하라.

                                                  - 감정
                                                  사랑스러움·감동·경이·대견·뿌듯·기쁨·안도·평온·걱정·조마조마·막막·미안·안쓰러움·자책·무기력·우울·귀여움·엉뚱·웃김·당황·허탈
                                                  이 중에서만 출력하라.

                                                  - 육아범주
                                                  수면, 식사, 사회성, 운동, 언어, 배변, 정서, 인지, 건강, 의복 이 중에서만 출력하라.
                                                  가장 적합성이 높은 하나만 출력하라.                                                

                                                  [Data]
                                                  {step1_insights}

                                                  [Output Format]
                                                  [N]. 문장원문: [문장 내용]
                                                  - 핵심어: 단어1, 단어2
                                                  - 감정: 슬픔, 기쁨
                                                  - 식사: 식사량 없으면 식사 횟수
                                                  - 배변: 기저귀와 화장실 관련 횟수
                                                  - 수면: 수면시간 없으면 시간대
                                                  - 시간: 오전/오후 시간                                                
                                                  - 체온: 체온
                                                  - 육아범주: 수면

                                                  [Output]""")

        try:
            model = self.get_ai_llm_label_model(config)

            chain = prompt | model | StrOutputParser()
            
            step2_keywords = await chain.ainvoke({"step1_insights": step1_insights})
            return step2_keywords.strip()
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Watsonx 2단계 라벨 추출 중 예외 발생: {str(e)}")
        

    async def ai_llm_diary_model_run_step3(self, perfect_match_input: str, config: dict) -> str:

        prompt = ChatPromptTemplate.from_template("""
                                                  너는 인스타그램에서 오늘 하루의 기록을 다정하고 솔직하게 독백 형태로 공유하는 대한민국 엄마이다.
                                                  제공된 [Data]의 '문장원문' 상황을 바탕으로, 명시된 '핵심어', '감정', '육아범주' 라벨 정보들을 조합하여 한 번호당 정확히 한 문장씩 자연스러운 한국어 일기를 작성해라.

                                                  [작성 규칙]
                                                  1. 맞춤법 및 글자 수: 국립국어원 표준 맞춤법과 띄어쓰기를 철저히 준수하세요. 제공된 '핵심어' 단어는 문장 속에 정확히 1회씩만 포함하여 자연스럽게 녹여내세요.
                                                  2. 문장 개수 1:1 대응: [Data]에 존재하는 번호의 개수와 동일한 개수의 문장으로만 작성하세요. 
                                                  3. 제공된 '문장원문'의 실제 맥락만 반영해야 하며, 한 문장이 완성될 때마다 반드시 줄바꿈을 하세요.
                                                  4. 시제 및 감정의 융합: '문장원문'에 나타난 행동 묘사 속에 2단계 '감정' 라벨 단어를 문맥에 맞게 직접 사용하여, 과거의 일을 회상하듯 따뜻한 뉘앙스로 서술하세요.
                                                  5. 생생한 문장의 시작: 문장을 시작할 때 행동의 대상이 되는 목적어나 시간, 장소, 상태를 나타내는 생생한 단어로 문장을 곧바로 시작하세요.
                                                  6. 연결 어미: 문장 중간의 연결 어미는 흐름을 매끄럽게 잇도록 구성하세요.
                                                  7. 종결 어미: 문장의 마지막 어미는 '~했네요', '~했답니다', '~하더라고요'와 같이 정갈하고 다정한 대화체 형식으로 자연스럽게 끝마치세요.
                                                  6. 한국어 전용 출력: 모든 문장은 오직 순수한 한글로만 작성하세요. 
                                                  8. 원문 자체에 한국어 외의 글자가 직접 적혀 있는 경우에만 해당 글자를 변형 없이 그대로 결과에 포함하여 출력하세요. 
                                                  9. 마감 기호: 모든 문장 작성을 완료한 바로 다음 줄에 무조건 [END] 라고만 출력하세요.

                                                  [Data]
                                                  {perfect_match_input}

                                                  [Diary]:""")

        try:
            model = self.get_ai_llm_diary_model(config)
            chain = prompt | model | StrOutputParser()
            
            raw_diary = await chain.ainvoke({"perfect_match_input": perfect_match_input})
            return raw_diary.strip()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Watsonx 3단계 일기 생성 중 예외 발생: {str(e)}")