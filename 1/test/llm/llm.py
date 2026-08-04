import os
import re
import asyncio
from typing import List, Dict, Any
from kiwipiepy import Kiwi
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams
import time  

class WatsonxDiaryGenerator:    
    def __init__(self):
        self.kiwi = Kiwi()
        self.dictionary_map = {"잘": "자다", "안": "않다", "못": "못하다"}


    def _get_watsonx_config(self) -> Dict[str, Any]:
        credentials = {"url": os.getenv("WATSONX_URL"), "apikey": os.getenv("WATSONX_APIKEY")}
        project_id = os.getenv("WATSONX_PROJECT_ID")

        if not credentials["apikey"] or not project_id:
            raise ValueError("환경 변수(WATSONX_APIKEY 또는 WATSONX_PROJECT_ID)가 누락되었습니다.")
        
        return {"credentials": credentials, "project_id": project_id}


    def run_step1_preprocessing(self, raw_text: str) -> str:
        refined_data = raw_text.strip().replace('\n', ' ')
        raw_lines = re.split(r'\.(?=\s|$)', refined_data)
        lines = [line.strip() + "." for line in raw_lines if line.strip()]
        
        step1_insights = ""
        for i, line in enumerate(lines):
            tokens = self.kiwi.tokenize(line)
            transformed_parts = []
            last_idx = 0
            j = 0
            
            while j < len(tokens):
                t = tokens[j]
                if t.tag in ["VV", "VA"]:
                    transformed_parts.append(line[last_idx:t.start])
                    lemma = t.form if t.form.endswith("다") else f"{t.form}다"
                    transformed_parts.append(lemma)
                    
                    end_idx = t.end
                    next_step = j + 1
                    while next_step < len(tokens):
                        if tokens[next_step].tag.startswith("E"):
                            end_idx = tokens[next_step].end
                            next_step += 1
                        else:
                            break
                    last_idx = end_idx
                    j = next_step
                    continue
                    
                elif t.tag == "MAG" and t.form in self.dictionary_map:
                    transformed_parts.append(line[last_idx:t.start])
                    transformed_parts.append(self.dictionary_map[t.form])
                    last_idx = t.end
                    
                j += 1
                
            transformed_parts.append(line[last_idx:])
            transformed_line = "".join(transformed_parts)
            transformed_line = re.sub(r'\s+', ' ', transformed_line).strip()
            if not transformed_line.endswith("."):
                transformed_line += "."
            transformed_line = re.sub(r'\s+\.', '.', transformed_line)

            step1_insights += f"{i+1}. {transformed_line}\n"

        return step1_insights.strip()


    def run_step2_label_extraction(self, step1_insights: str, config: dict) -> str:
        extract_params = {
            GenParams.DECODING_METHOD: "greedy",
            GenParams.MIN_NEW_TOKENS: 1,
            GenParams.MAX_NEW_TOKENS: 300,
            GenParams.REPETITION_PENALTY: 1.2,
        }

        extractor_model = ModelInference(
            model_id="mistralai/mistral-small-3-1-24b-instruct-2503",
            credentials=config["credentials"],
            params=extract_params,
            project_id=config["project_id"]
        )

        extract_prompt_template = """[Instruction]
        당신은 육아 기록 전문가입니다. 
        주어진 [Data]의 각 문장을 순서대로 정밀 분석하여 아래 [Output Format] 양식에 맞춰 오직 핵심 라벨 결과만 깨끗하게 출력하세요. 
        원문의 글자 형태를 절대로 임의로 변형하거나 깨뜨리지 마십시오.
        원문의 행동 주체가 누구인지 확실히 해라.

        핵심어
        주체(누가)·행동(무엇을 하다)·대상(무엇을)·장소(어디서)·시간(언제)·이유(왜)·상태(어떠한가)·방식(어떻게)·결과(어떻게 되다)·수치(얼마나)·상대(누구와)·감정(어떤 기분으로)·대책(어떻게 대처했나) 
        이 중에서 문장에 존재하는 것들만 사전에 적혀있는 형태로 출력하라.

        감정
        사랑스러움·감동·경이·대견·뿌듯·기쁨·안도·평온·걱정·조마조마·막막·미안·안쓰러움·자책·무기력·우울·귀여움·엉뚱·웃김·당황·허탈

        이 중에서 감정의 주인이 누군인지 같이 출력하라.

        육아범주는 수면, 식사, 사회성, 운동, 언어, 배변, 정서, 인지, 건강, 의복 이것들 중에서 출력하라.

        핵심어, 감정, 육아범주는 채워져 있어야 한다.
        수치가 없으면 없음으로 표시하라.

        [Data]
        {step1_insights}

        [Output Format]
        1. 문장원문: [문장 내용]
        - 핵심어: 단어1, 단어2
        - 감정: 슬픔, 기쁨
        - 식사: 식사량 출력 없으면 식사 횟수 출력 
        - 배변: 기저귀와 화장실 관련 횟수 출력
        - 수면: 수면시간 출력 없으면 시간대 출력
        - 체온: 체온 수치
        - 육아범주: 수면

        [Output]
        """

        final_extract_prompt = extract_prompt_template.format(step1_insights=step1_insights)
        extract_response = extractor_model.generate(prompt=final_extract_prompt)
        step2_keywords = ""

        try:
            if isinstance(extract_response, dict) and 'results' in extract_response:
                results_list = extract_response['results']

                if results_list and isinstance(results_list, list):
                    step2_keywords = results_list[0].get('generated_text', '').strip()

            else:
                step2_keywords = str(extract_response).strip()

        except Exception:
            step2_keywords = str(extract_response).strip()
            
        return step2_keywords

    def run_step3_diary_writing(self, perfect_match_input: str, config: dict) -> str:
        creative_params = {
            GenParams.DECODING_METHOD: "sample",
            GenParams.MIN_NEW_TOKENS: 45,
            GenParams.MAX_NEW_TOKENS: 208,
            GenParams.REPETITION_PENALTY: 1.05,
            GenParams.TEMPERATURE: 0.2,
            GenParams.TOP_P: 0.8,
            GenParams.STOP_SEQUENCES: ["\n\n", "[END]"]
        }


        writer_model = ModelInference(
            model_id="meta-llama/llama-3-3-70b-instruct",
            credentials=config["credentials"],
            params=creative_params,
            project_id=config["project_id"]
        )


        diary_prompt_template = """너는 인스타그램에서 오늘 하루의 기록을 다정하고 솔직하게 독백 형태로 공유하는 대한민국 엄마이다.
        제공된 [육아 데이터 블록]의 '문장원문' 상황을 베이스로 삼고, 여기에 명시된 '핵심어', '감정', '육아범주' 라벨 정보들을 완벽하게 결합하여 한 번호당 정확히 한 문장씩 자연스러운 한국어 일기를 작성해라.

        [출력 예시 - 이 자연스러운 문장 구조와 어투만 참고하여 라벨 정보를 문장으로 만드세요]
        출근길에 지하철을 바로 타서 지각하지 않고 제시간에 안전하게 도착했네요.
        칭찬받으려고 열심히 준비한 기획안을 부장님이 보시고 활짝 웃어주셔서 정말 뿌듯했답니다.
        퇴근하고 집으로 돌아와 따뜻한 물로 샤워를 하니 하루의 피로가 싹 풀리더라고요.
        산책하러 나가서 잔디밭을 신나게 뛰놀고 집으로 얌전하게 돌아왔네요.
        기특해서 털에 묻은 먼지를 털어주고 부드럽게 쓰다듬어 주었답니다.
        고맙다는 듯이 꼬리를 살랑살랑 흔들며 안기는데 하루의 스트레스가 싹 풀리더라고요.

        [작성 규칙 - 절대 준수]
        0. 맞춤법: 국립국어원 맞춤법과 띄어쓰기를 준수해서 작성해라. 핵심어를 사용횟수는 한번이다.
        1. 문장 개수 1:1 일치: [육아 데이터 블록]의 번호 개수와 똑같은 개수의 문장만 작성해라. 오직 제공된 '문장원문'의 현실적인 상황 맥락만을 충실히 바탕으로 작성해라. 
        상황을 분석할 때 행동의 주체가 누구인지 확실히 구분해라. 한 문장이 끝날 때마다 무조건 줄바꿈을 해라.
        2. 자연스러운 감정 및 시제 반영: 
        - '문장원문'에 나타난 행동의 주체를 파악해서 작성해라.
        - '문장원문'에 나타난 행동 묘사 속에 2단계 '감정' 라벨 단어의 정서를 녹여 과거의 일을 회상하듯 작성해라.
        - 자연스럽게 '감정' 라벨 단어를 사용하라.
        - 데이터의 핵심어를 문맥에 맞게 서술형으로 작성해라.
        3. 주어 및 목적어: 문장 시작할 때 상투적이지 않고 신선한 주어나 목적어를 써라. 핵심어 단어 원형에 조사와 어미를 자연스럽게 융합하여, 생생한 행동이나 상황 묘사로 문장을 곧바로 시작해라.
        4. 연결 어미 사용: 문장 중간에 사용한 어미는 새로운 문장 작성시에 다시 사용해라. 문장을 매끄럽게 연결하여 자연스럽게 작성하라.
        5. 문장 마감 어미: 문장의 마지막 어미는 정갈한 대화 형식으로 자연스럽게 끝마쳐라.
        6. 깨끗한 한글 출력: 문장은 오직 순수한 한글로만 작성해야 하며, 외국어의 경우 오직 제공된 라벨에 명시되어 있는 경우에만 제한적으로 포함하여 출력해라.
        7. 주체 제외: 문장의 주체는 대부분 아기이다. 주체 없이 작성하라.
        8. 마감 기호: 모든 문장 작성을 마친 바로 다음 줄에 무조건 [END] 라고만 출력해라.

        [육아 데이터 블록]
        {perfect_match_input}

        [Diary]:"""

        final_diary_prompt = diary_prompt_template.format(perfect_match_input=perfect_match_input)
        writer_response = writer_model.generate(prompt=final_diary_prompt)

        raw_diary = ""

        try:
            if isinstance(writer_response, dict) and 'results' in writer_response:
                raw_diary = writer_response['results'][0]['generated_text'].strip()

            else:
                raw_diary = str(writer_response).strip()

        except Exception:
            raw_diary = str(writer_response).strip()
            
        return raw_diary

    def run_step4_cleansing(self, raw_diary: str) -> List[str]:
        if "[END]" in raw_diary:
            raw_diary = raw_diary.split("[END]")[0].strip()

        raw_lines = [line.strip() for line in raw_diary.split('\n') if line.strip()]
        full_print_lines = []

        for line in raw_lines:
            line = re.sub(r'^\d+[\.\s\-~)]+|^\s*\[\d+[^\]]*\]', '', line).strip()
            line = re.sub(r'[\u4e00-\u9fff]', '', line)
            line = re.sub(r'[^가-힣a-zA-Z0-9\s\.,!\?\'\"~%·]', '', line).strip()

            if line:
                full_print_lines.append(line)


        def truncate_by_bytes(text, max_bytes=400):
            text_bytes = text.encode('utf-8')

            if len(text_bytes) <= max_bytes:
                return text
            
            return text_bytes[:max_bytes - 3].decode('utf-8', errors='ignore').strip() + "..."

        return [truncate_by_bytes(line, 400) for line in full_print_lines]


    def parse_categories_for_db(self, step2_keywords: str) -> Dict[str, str]:
        categories = {
            "d_eat": None,
            "d_sleep": None,
            "d_toilet": None,
            "d_temp": None,
            "d_label": "육아 기록"
        }

        found_categories = re.findall(r'육아범주:\s*([가-힣\s,]+)', step2_keywords)
        all_categories_set = set()

        for cat_line in found_categories:
            words = [w.strip() for w in re.split(r'[\s,]+', cat_line) if w.strip()]
            all_categories_set.update(words)
            
        if all_categories_set:
            categories["d_label"] = ", ".join(sorted(list(all_categories_set)))

        found_metrics = re.findall(r'수치:\s*([가-힣a-zA-Z0-9\s\.\(\)]+)', step2_keywords)
        combined_metrics = " ".join(found_metrics)
        
        clean_metric = re.sub(r'[\(\)]', '', combined_metrics).strip()
        
        if not clean_metric or any(no_val in clean_metric for no_val in ["없음", "존재", "미기재"]):
            clean_metric = ""

        combined_words = " ".join(found_categories)

        if "식사" in combined_words and clean_metric:
            categories["d_eat"] = clean_metric
            
        if "수면" in combined_words and clean_metric:
            categories["d_sleep"] = clean_metric
            
        if "배변" in combined_words and clean_metric:
            categories["d_toilet"] = clean_metric
            
        if clean_metric and ("건강" in combined_words or any(t in clean_metric for t in ["도", "체온", "."])):
            categories["d_temp"] = clean_metric

        return categories

    async def execute_async_pipeline(self, raw_text: str) -> Dict[str, Any]:
        config = self._get_watsonx_config()
        loop = asyncio.get_running_loop()

        total_start_time = time.time()


        step1_start = time.time()
        step1_insights = await loop.run_in_executor(None, self.run_step1_preprocessing, raw_text)
        step1_duration = time.time() - step1_start
        print("\n=== 1단계: 구조화된 요약 메모 추출 완료 ===")
        print(step1_insights)
        print(f"[1단계 Kiwi 소요 시간]: {step1_duration:.3f}초")


        step2_start = time.time()
        step2_keywords = await loop.run_in_executor(None, self.run_step2_label_extraction, step1_insights, config)
        step2_duration = time.time() - step2_start
        print("\n=== 2단계: 주요 라벨 단어 추출 완료 ===")
        print(step2_keywords)
        print(f"[2단계 Mistral 소요 시간]: {step2_duration:.3f}초")

        if not step2_keywords:
            raise RuntimeError("2단계 핵심 라벨 추출에 실패했습니다.")


        step3_start = time.time()
        raw_diary = await loop.run_in_executor(None, self.run_step3_diary_writing, step2_keywords, config)
        final_lines = await loop.run_in_executor(None, self.run_step4_cleansing, raw_diary)
        step3_duration = time.time() - step3_start
        
        print("\n=== 3단계: 최종 완성된 감성 일기 ===")
        for idx, final_line in enumerate(final_lines):
            print(f"[{idx+1}] {final_line}")
        print(f"[3&4단계 Llama 생성 및 정제 소요 시간]: {step3_duration:.3f}초")


        total_duration = time.time() - total_start_time
        print("\n" + "="*50)
        print(f"[전체 파이프라인 가동 완료]: 총 {total_duration:.2f}초 소요되었습니다.")
        print("="*50)

        db_categories = self.parse_categories_for_db(step2_keywords)

        return {
            "step1_insights": step1_insights,
            "step2_keywords": step2_keywords,
            "final_diary": "\n".join(final_lines),
            "db_categories": db_categories
        }


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv

    load_dotenv()

    test_memo = """
    오늘 아이가 아침부터 컨디션이 최고였는지 싱글벙글 웃으며 잘 놀 기세였습니다. 점심 이유식을 다 비우고도 더 달라고 칭얼거렸는데, 이상하게 낮 시간이 지나도 침대에 누워 잘 생각이 전혀 없어 보였습니다. 다행히 3시쯤 유모차를 타자마자 스르륵 잠들어 1시간 동안 땀을 흘리며 푹 잤습니다. 체온은 36.6도입니다."""

    async def main_test():
        print("[AI 독립 테스트] 파이프라인 가동을 시작합니다...")
        
        generator = WatsonxDiaryGenerator()
        
        try:
            result = await generator.execute_async_pipeline(test_memo)
            
            print("\n" + "="*40)
            print("[AI 독립 테스트 완료] 반환된 최종 딕셔너리 구조")
            print("="*40)
            print(f"▶ 1단계 구조화 요약 샘플 (일부): {result['step1_insights'][:50]}...")
            print(f"▶ 2단계 키워드 라벨 추출 결과 완료")
            print(f"▶ DB 필드 자동 매핑 아웃풋: {result['db_categories']}")
            print("-"*40)
            print("▶ 최종 정제 완료된 일기 본문:")
            print(result['final_diary'])
            print("="*40)
            
        except Exception as e:
            print(f"테스트 중 에러 발생: {e}")

    asyncio.run(main_test())