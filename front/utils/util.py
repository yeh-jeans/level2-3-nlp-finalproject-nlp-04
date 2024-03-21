__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

from io import BytesIO
from PIL import Image
import base64
import streamlit as st
import pandas as pd
import os
from langchain.embeddings import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferWindowMemory
from langchain.prompts import PromptTemplate
from langchain.chains import ConversationChain

sys.path.append('./')
from back.config import OPENAI_API_KEY

def load_css_as_string(file_name):
    with open(file_name,'r') as f:
        css = f"""{f.read()}"""
    return css

def local_css(file_name):
    with open(file_name) as f:
        st.markdown(f'''<style>{f.read()}</style>''', unsafe_allow_html=True)

def set_background(fav_image_path,logo_image_path):
    FAV = Image.open(fav_image_path)
    st.markdown(
        """
    <style>
        [data-testid="collapsedControl"] {
            display: none
        }
    </style>
    """,
        unsafe_allow_html=True,
    )
    # header, main, footer 설정
    set_index(logo_image_path)
    

def get_image_base64(image_path):
    image = Image.open(image_path)
    buffered = BytesIO()
    image.save(buffered, format="png")
    image_str = base64.b64encode(buffered.getvalue()).decode()
    return image_str

def set_index(logo_image_path):
    # header/footer/main_context layout css hack
    st.markdown( """ <style>
                @import url(https://cdn.rawgit.com/moonspam/NanumSquare/master/nanumsquare.css);
                header {
                    visibility : hidden;
                }
                body, body div, p, span {
                    font-family: 'Nanumsquare', 'Malgun Gothic' !important;
                }
                .css-qcqlej{
                    flex-grow:1;
                }
                footer {
                    visibility: visible;
                    background: #2D5AF0;

                }
                .css-164nlkn {
                    display : flex;
                    color : #2D5AF0;
                    max-width : 100%;
                    height : 4rem;
                    padding-top : 1rem;
                    padding-bottom : 1rem
                }
                footer a {
                    visibility: hidden;
                }
                footer {
                    font-family : "Nanumsquare";
                }
                footer:after {
                    visibility: visible; 
                    content:"ⓒ 2023. 인포스톰 All rights reserved";
                    font-weight: 700;
                    font-size: 15px;
                    color: #FFFFFF;
                    align-self : center;
                }
                .css-z5fcl4 {
                padding-left : 10%;
                padding-right : 10%;
                padding-top : 2rem !important;
                display : flex !important;  
                }

                </style> """, unsafe_allow_html=True)
    
    # Logo input & logo css hack
    # logo_img = get_image_base64('.\img\logo_char.jpg')
    logo_img = get_image_base64(logo_image_path)
    st.markdown("""<style>
                    .main-logo {
                        padding-bottom: 1rem;
                    }
                </style>""", unsafe_allow_html=True)
    st.markdown(f'''<a class="main-logo" href="/main" target="_self">
                    <img src="data:img\logo_char.jpg;base64,{logo_img}" width="240px"; height="70px";/>
                </a>''', unsafe_allow_html=True)


# 필수 요소 전부 들어있는지 체크하는 함수
def check_essential():
    '''
    이름, 지원 직무, 이력서가 있어야 합니다!
    면접관은 기본 세팅값이 있어서 괜찮!
    '''
    check_result = []
    josa =''
    if not st.session_state.user_name:
        check_result.append('이름')
        josa += '이'
    if st.session_state.selected_job == '검색 또는 선택':
        check_result.append('지원 직무')
        josa += '가'
    if not st.session_state.uploaded_resume:
        check_result.append('이력서')
        josa += '가'
    # 추가된 코드 @@@@@@@@@@@@@@@@@@
    if not st.session_state.uploaded_JD:
        check_result.append('채용 공고')
        josa += '가'
    return check_result,josa

def read_sample_resume(path):
    with open(path, 'rb') as s1:
        data = s1.read()
    return data
    
def read_gif(path):
    with open(path, 'rb') as f:
        data = f.read()
        data = base64.b64encode(data).decode("utf-8")
    return data

def read_job_info_tb(path):
    job_info = pd.read_parquet(path, engine='pyarrow')
    job_info = job_info[(job_info.version == 'v2')].reset_index(drop=True)
    
    JOBS = ['검색 또는 선택'] + sorted(job_info['job_nm'].tolist())
    return job_info,JOBS

def read_user_job_info(job_tb,selected_job): # kpi 는 핵심역량. 
    job_prompt, job_kpi_dic = job_tb[(job_tb.job_nm == selected_job)][['prompt', 'job_kpi_list']].values[0]
    #job_kpi_dic = job_tb[(job_tb.job_nm == selected_job)][['prompt', 'job_kpi_list']].values[0]
    # 데이터 프레임에서 [(job_tb.job_nm == selected_job)] 조건에 맞는 거에서 [['prompt', 'job_kpi_list']] 인 데이터프레임을 반환함
    # job_kpi_dic = eval(job_kpi_dic) # String Dic을 Dic화 시켜줌. 
    # 여기서 자꾸 eval 에서 null 값이 있따고 오류가 나서 아래 코드로 바꿔줌
    #job_kpi_dic = job_kpi_dic.replace('\x00', '')
    job_kpi_dic = eval(job_kpi_dic)

    job_nm = st.session_state.selected_job
    job_ability = ", ".join(job_kpi_dic['핵심역량list'])

    # print(job_nm, job_ability)
    return job_nm,job_ability

def read_prompt_from_txt(path):
    with open(path,"r",encoding='utf-8') as f:
        data = f.read()
    return data

# 사용자 입력 텍스트를 파일로 저장하여 경로를 반환하는 함수
# save_directory, filename="uploaded_jd.txt" 이 파일이 존재하면 그 파일을 열어 내용을 넣고 저장합니다. 
def save_uploaded_jd_as_filepath(uploaded_jd, save_directory, filename="uploaded_jd.txt"):
    file_path = os.path.join(save_directory, filename)
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(uploaded_jd)
    return file_path


os.environ['OPENAI_API_KEY'] = OPENAI_API_KEY



@st.cache_resource
def load_chain(question):
    """
    The `load_chain()` function initializes and configures a conversational retrieval chain for
    answering user questions.
    :return: The `load_chain()` function returns a ConversationalRetrievalChain object.
    """

    # Load OpenAI embedding model
    embeddings = OpenAIEmbeddings()
    
    # Load OpenAI chat model
    llm = ChatOpenAI(temperature=0)
    template = read_prompt_from_txt(os.path.join(os.path.dirname(os.path.dirname(__file__)),"data", "tail_question_template.txt"))
    
    # Create memory 'chat_history' 
    memory = ConversationBufferWindowMemory(human_prefix="면접자 답변", ai_prefix='answer')
    memory.save_context({'input':''},{'output':question})
    # Create system prompt
    prompt = PromptTemplate(input_variables = ['history','input'],template = template)
     # Create the Conversational Chain
    chain = ConversationChain(llm = llm,verbose = False,memory=memory, prompt = prompt)
    
    return chain