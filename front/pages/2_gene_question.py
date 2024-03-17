__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import streamlit as st
from streamlit_extras.switch_page_button import switch_page
import time
import traceback
import os
import re
import random
from etc.src.generate_question import (preprocess_questions,
                                   load_user_resume,
                                   save_user_resume,
                                   # 추가
                                   load_user_JD, 
                                   save_user_JD,
                                   create_prompt_with_jd,
                                   create_prompt_with_resume,
                                   create_resume_vectordb
                                   )
from etc.utils.util import (
                        read_user_job_info,
                        read_prompt_from_txt,
                        local_css,
                        load_css_as_string)
import base64 # gif 이미지 불러오기
from langchain.document_loaders import PyPDFLoader
from langchain.chat_models import ChatOpenAI
from langchain.chains import SequentialChain
from langchain.callbacks import get_openai_callback


from langchain.chains import RetrievalQA
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain_community.chat_models import ChatOpenAI
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain.prompts import PromptTemplate
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain.chains import LLMChain

import tiktoken
import chromadb
import yaml

# YAML 파일 로드
with open("secret_key.yaml", "r") as yaml_file:
    config = yaml.safe_load(yaml_file)


st.session_state.logger.info("start")
NEXT_PAGE = 'show_questions'

OPENAI_API_KEY = config['OPENAI_API_KEY']
OPENAI_API_KEY_DIR = 'api_key.txt'
DATA_DIR = config['STREAMLIT']['DATA_DIR']

#### style css ####
MAIN_IMG = st.session_state.MAIN_IMG
LOGO_IMG = st.session_state.LOGO_IMG

# text_splitter = CharacterTextSplitter(
#     chunk_size=200,
#     chunk_overlap=20
#     )


local_css('etc/css/background.css')
local_css("etc/css/2_generate_question.css")
st.markdown(f"""<style>
                         /* 로딩이미지 */
                         .loading_space {{
                            display : flex;
                            justify-content : center;
                            margin-top : -3rem;
                        }}
                        .loading_space img{{
                            max-width : 70%;
                        }}
                        .loading_text {{
                            /* 광고 들어오면 공간 확보 */
                            padding-top : 4rem;
                            z-index : 99;
                        }}
                        .loading_text p{{
                            font-family : 'Nanumsquare';
                            color:#4C4F6D;
                            font-size:28px ;
                            line-height:1.5;
                            word-break:keep-all;
                            font-weight:700;
                            text-align:center;
                            z-index : 99;
                        }}
                        .dots-container {{
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100%;
                            width: 100%;
                            padding-top : 2rem;
                            padding-bottom : 5rem;
                            z-index : 99;
                        }}

                        .dot {{
                            z-index : 99;
                            height: 20px;
                            width: 20px;
                            margin-right: 10px;
                            border-radius: 10px;
                            background-color: #b3d4fc;
                            animation: pulse 1.5s infinite ease-in-out;
                        }}
                        .dot:last-child {{
                            margin-right: 0;
                        }}

                        .dot:nth-child(1) {{
                            animation-delay: -0.3s;
                        }}

                        .dot:nth-child(2) {{
                            animation-delay: -0.1s;
                        }}

                        .dot:nth-child(3) {{
                            animation-delay: 0.1s;
                        }}
                        </style>
#             """,  unsafe_allow_html=True)
## set variables
MODEL_NAME = 'gpt-3.5-turbo-16k'
INTERVIEWER_NAME = {
    '0.5' : '혁신수',
    '0.7' : '정의현',
    '0.9' : '조화린'
    }

#
 
 
## st.session_state["save_dir"] = logs/user/952d63ba-3e50-43d6-91dd-dcb2b5e0b10a
 
## set save dir
USER_RESUME_SAVE_DIR = os.path.join(st.session_state["save_dir"],'2_generate_question_user_resume.pdf')
### 추가
USER_JD_SAVE_DIR = os.path.join(st.session_state["save_dir"],'2_generate_question_user_JD.txt')

BIG_QUESTION_SAVE_DIR = os.path.join(st.session_state["save_dir"],'2_generate_question_generated_big_question.txt')

# 원본은 read_user_job_info 를 이용해 사용자가 정한 직군에 따라 정해진 프롬프트와 핵심역량을 이용해 사용합니다.
# 우리는 그런것 없이,  STEP 1. JD 를 GPT 를 통해 한번 요약하고, 
# STEP 2. 요약한 JD 를 다시 이력서 내용과 함께 GPT 에 QA 프롬프트와 함께 질의
# STEP 3. 답변을 /n/n 기준으로 잘라 변수에 저장 후 다음 페이지로 넘김.


# 진행률
progress_holder = st.empty() # 작업에 따라 문구 바뀌는 곳
loading_message = [f"'{INTERVIEWER_NAME[str(st.session_state.temperature)]}' 면접관이 '{st.session_state.user_name}'님의 이력서를 꼼꼼하게 읽고 있습니다. <br> 최대 3분까지 소요될 수 있습니다.",
                f"'{INTERVIEWER_NAME[str(st.session_state.temperature)]}' 면접관이 '{st.session_state.user_name}'님과의 면접을 준비하고 있습니다"]

# 로딩 그림(progress bar)
st.markdown("""<section class="dots-container">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </section>
            """,  
            unsafe_allow_html=True)

## 면접&이력서 팁
## 공간이자 이미지가 들어가면 좋을 것 같은 곳
st.markdown(f'''<div class='loading_space'>
                    <img class='tips' src="data:image/gif;base64,{st.session_state['LOADING_GIF1']}"></div>''',unsafe_allow_html=True)
with progress_holder:
    for i in range(2):
        ### step1 : 대질문 생성 및 추출, step2 : 전처리(time.sleep(3))
        progress_holder.markdown(f'''<div class="loading_text">
                                        <p>{loading_message[i]}</p></div>''', unsafe_allow_html=True)
        if st.session_state.big_q_progress:
            ### 이력서 Pre-process
            st.session_state.logger.info("resume process ")
            ### uploaded_file는 streamlit의 file_uploader에서 반환된 객체
            uploaded_file = st.session_state.uploaded_resume
            ### 저장
            save_user_resume(USER_RESUME_SAVE_DIR,uploaded_file)
            st.session_state.logger.info("save resume")
            ### 불러오기
            user_resume = load_user_resume(USER_RESUME_SAVE_DIR)
            st.session_state.logger.info("user total resume import")
            
            
            ### JD Pre-process @@@@@@@@@@@@@@@@@@@@@@@@@@
            st.session_state.logger.info("JD precess")
            ### uploaded_txt 로 uploaded_JD 에서 JD 를 받아옵니다
            uploaded_file = st.session_state.uploaded_JD
            ### 저장 USER_JD_SAVE_DIR 경로에 uploaded_file 내용을 적어 저장합니다. 
            save_user_JD(USER_JD_SAVE_DIR,uploaded_file)
            st.session_state.logger.info("save JD")
            ### 불러오기
            user_JD = load_user_JD(USER_JD_SAVE_DIR)
            st.session_state.logger.info("user total JD import")
            
            ### JD 사용하여 JD 추출용 프롬프트 만들기
            st.session_state.logger.info("prompt JD start")
            
            prompt_template = read_prompt_from_txt( DATA_DIR + "test/prompt_JD_template.txt")
            
            prompt_JD = create_prompt_with_jd(prompt_template)
            # prompt_JD 생성완료
            st.session_state.logger.info("create prompt JD object")
            
            ### 모델 세팅 그대로
            llm = ChatOpenAI(temperature=st.session_state.temperature
                            , model_name=MODEL_NAME
                            , openai_api_key=OPENAI_API_KEY
                            )
            
            st.session_state.logger.info("create llm object")
            
            
            ######## 이제 태연스의  데모를 체인으로 바꿔 실행하겠습니다. 
            # STEP 1. 사용자가 입력한 JD 를 GPT 를 이용해 job_description 을 뽑습니다.

            # 사용 시간 출력용 
            start = time.time()
            
            chain_JD_1 = LLMChain(llm=llm, prompt=prompt_JD)  
            
            
            st.session_state.logger.info("create chain_JD_1 object")
            
            job_description = chain_JD_1.run(user_JD)
            
            st.session_state.logger.info("chain_JD_1 complit")
            
            
            # STEP 2. step 1 에서 생성된 job_description 를 qa prompt template 에 넣고, GPT 에 질의하여 예상 질문을 뽑습니다.
            # prompt_qa_template #######################################
            
            st.session_state.logger.info("prompt QA start")
            
            prompt_template = read_prompt_from_txt( DATA_DIR + "test/prompt_qa_template")
            
            
            st.session_state.logger.info("create prompt QA template")

            vector_index = create_resume_vectordb(USER_RESUME_SAVE_DIR) # 이력서 vectordb를 생성해줍니다.


            
            
            prompt_qa = create_prompt_with_resume(prompt_template)
            
            st.session_state.logger.info("create prompt_qa")
            
            vector_index = create_resume_vectordb(USER_RESUME_SAVE_DIR) # 이력서 vectordb를 생성해줍니다.
            # loader = PyPDFLoader(USER_RESUME_SAVE_DIR)
            # pages = loader.load_and_split(text_splitter)
            
            # vector_index = Chroma.from_documents(
            #     pages, # Documents
            #     OpenAIEmbeddings(),) # Text embedding model
            
            st.session_state.logger.info("user_resume chunk OpenAIEmbeddings ")

            ### STEP 2 를 위한 새 모델 호출

            llm2 = ChatOpenAI(temperature=0.0
                            , model_name=MODEL_NAME
                            , openai_api_key=OPENAI_API_KEY
                            )
            
            chain_type_kwargs = {"prompt": prompt_qa}
            
            qa_chain = RetrievalQA.from_chain_type(
                llm=llm2,
                chain_type="stuff",
                retriever=vector_index.as_retriever(),
                chain_type_kwargs=chain_type_kwargs, verbose = True)
            
            main_question = qa_chain.run(job_description)
            
            print("prompt_qa @@@@@@@@",prompt_qa)
            
            st.session_state.logger.info(" prompt_qa running complit")
            
            print(main_question)
            
            
            

            end = time.time()
            st.session_state.logger.info(f"generate big question run time is ... {(end-start)/60:.3f} 분 ({(end-start):0.1f}초)")
            
            ### STEP 3. 결과물 및 Token 사용량 저장
            ### 결과 텍스트 저장
            # '\n\n'을 사용하여 질문 분리 후 바로 unpacking
            

            
            # 각 항목을 분리하여 리스트에 저장
            questions = re.split(r'\n\d+\.\s*', main_question.strip())
            #    첫 번째 빈 항목 제거
            questions = [question for question in questions if question]


            
            
            # ### Token 사용량 기록
            # total_tokens, prompt_tokens, completion_tokens = calculate_token_usage(prompt_qa, main_question)


            # st.session_state.logger.info(f"QA tokens used: {total_tokens}")
            # st.session_state.logger.info(f"QA Prompt tokens: {prompt_tokens}") 
            # st.session_state.logger.info(f"Completion tokens: {completion_tokens}")
            
            # ### 문장앞 숫자 삭제. 질문 전처리
            #questions = remove_numeration_from_questions(questions)
            
            st.session_state.logger.info(f"save question result")
            
            print("난 코딩이너무좋아",questions[0])

            ### User pdf파일 삭제
            try:
                os.remove(USER_RESUME_SAVE_DIR)
            except Exception as e:
                st.session_state.logger.info(f"User resume delete Error: \n{e}")
                print(">>> User resume delete Error: \n{e}")

            st.session_state.big_q_progress = False ### 대질문 생성 끝
        else :


            ### 다음 세션으로 값 넘기기
            st.session_state.main_question = questions
            st.session_state.logger.info("end gene_question")
            time.sleep(3)
            ####
            switch_page(NEXT_PAGE)