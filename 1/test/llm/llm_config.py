import os
from typing import Dict, Any
from dotenv import load_dotenv

# .env 파일에 있는 변수들을 메모리로 로드합니다.
load_dotenv()

def get_watsonx() -> Dict[str, Any]:
    url = os.getenv("WATSONX_URL")
    apikey = os.getenv("WATSONX_APIKEY")
    project_id = os.getenv("WATSONX_PROJECT_ID")


    if not url or not apikey or not project_id:
        raise ValueError("환경 변수(WATSONX_URL, WATSONX_APIKEY, WATSONX_PROJECT_ID) 중 누락된 값이 있습니다.")
    
    return {
        "credentials": {
            "url": url,
            "apikey": apikey
        },
        "project_id": project_id
    }
