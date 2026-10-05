import pandas as pd
import json
import re

def clean_text(text):
    if pd.isna(text):
        return ""
    return str(text).strip()

def extract_questions(xls, sheet_name):
    print(f"\n--- Parsing {sheet_name} ---")
    df = pd.read_excel(xls, sheet_name=sheet_name)

    header_idx = -1
    for i in range(min(15, len(df))):
        row_vals = [str(x).lower() for x in df.iloc[i].values]
        if any('question' in v and 'label' in v for v in row_vals):
            header_idx = i + 1
            break

    if header_idx != -1:
        df = pd.read_excel(xls, sheet_name=sheet_name, header=header_idx)
    else:
        df = pd.read_excel(xls, sheet_name=sheet_name, header=1)

    col_map = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if 'question & ui label' in col_lower:
            col_map['question'] = col
        elif 'required?' in col_lower:
            col_map['required'] = col
        elif 'control type' in col_lower:
            col_map['type'] = col
        elif 'allowable range' in col_lower:
            col_map['options'] = col

    sections_dict = {}
    current_section = "General"

    for index, row in df.iterrows():
        try:
            # The structure appears to be:
            # Column 0: Q# (can be NaN or Section Name or Question ID)
            # Column 1: Question Type/Category (subsection)
            # Column 2: Question & UI Label

            # The issue with my previous parsing is that if Q# was NaN, I wasn't updating the current_section if it was written in the Question Type/Category column.
            # Some sections might not have "Section X:" prefix, but just be a bold header in the first/second column.

            q_val = str(row[df.columns[0]]).strip()

            # 1. Update the Main Section if the Q# column looks like a Section header
            if q_val.lower().startswith('section'):
                current_section = q_val
                print(f"  Found Major Section in col 0: {current_section}")
                continue

            # If col 0 is NaN but col 1 has a value and col 2 is NaN, it might be a section header
            if pd.isna(row[df.columns[0]]) and len(df.columns) > 1 and not pd.isna(row[df.columns[1]]) and pd.isna(row[df.columns[2]]):
                val = str(row[df.columns[1]]).strip()
                if val.lower().startswith('section'):
                    current_section = val
                    print(f"  Found Major Section in col 1: {current_section}")
                    continue

            # 2. Extract Question Text
            if 'question' in col_map and not pd.isna(row[col_map['question']]):
                q_text = str(row[col_map['question']]).strip()
                if q_text == '' or q_text == 'nan' or 'Q#' in q_text or 'Question & UI Label' in q_text:
                    continue

                # Skip instructional text
                if 'green denotes' in q_text.lower() or '--- denotes' in q_text.lower() or 'this form opens' in q_text.lower():
                    continue

                # 3. Handle sub-sections (Category) if available
                subsection = ""
                if len(df.columns) > 1 and not pd.isna(row[df.columns[1]]):
                    potential_sub = str(row[df.columns[1]]).strip()
                    if potential_sub and potential_sub.lower() != 'nan':
                        subsection = potential_sub

                req = False
                if 'required' in col_map and not pd.isna(row[col_map['required']]):
                    req_str = str(row[col_map['required']]).strip().lower()
                    req = 'yes' in req_str or 'required' in req_str

                q_type = 'text input'
                if 'type' in col_map and not pd.isna(row[col_map['type']]):
                    q_type = str(row[col_map['type']]).strip().lower()

                options = []
                if 'options' in col_map and not pd.isna(row[col_map['options']]):
                    opts_raw = str(row[col_map['options']])
                    if not any(t in q_type for t in ['text input', 'number input', 'email input', 'phone input', 'numeric']):
                        if '\n' in opts_raw:
                            options = [o.strip() for o in opts_raw.split('\n') if o.strip()]
                        elif ',' in opts_raw and not 'min:' in opts_raw.lower() and not 'valid' in opts_raw.lower():
                            options = [o.strip() for o in opts_raw.split(',') if o.strip()]
                        else:
                            options = [opts_raw.strip()]

                        options = [re.sub(r'^[-•*]\s*', '', o) for o in options if o]
                        options = [o for o in options if not o.lower().startswith('none (')]

                if current_section not in sections_dict:
                    sections_dict[current_section] = []

                sections_dict[current_section].append({
                    'subsection': subsection,
                    'text': q_text,
                    'required': req,
                    'type': q_type,
                    'options': options
                })
        except Exception as e:
            print(f"Error on row {index}: {e}")

    # Convert to list of sections
    sections_list = []
    for section_name, questions in sections_dict.items():
        if questions:
            sections_list.append({
                'title': section_name,
                'questions': questions
            })

    num_q = sum(len(s['questions']) for s in sections_list)
    print(f"Found {num_q} questions across {len(sections_list)} major sections for {sheet_name}")
    return sections_list

def parse_pre_survey(xls):
    print("\n--- Parsing Pre-Survey ---")
    df = pd.read_excel(xls, sheet_name='2.1_Pre-Survey.')

    header_idx = -1
    for i in range(min(15, len(df))):
        row_vals = [str(x).lower() for x in df.iloc[i].values]
        if any('question' in v and 'label' in v for v in row_vals):
            header_idx = i + 1
            break

    if header_idx != -1:
        df = pd.read_excel(xls, sheet_name='2.1_Pre-Survey.', header=header_idx)
    else:
        df = pd.read_excel(xls, sheet_name='2.1_Pre-Survey.', header=1)

    col_map = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if 'question & ui label' in col_lower:
            col_map['question'] = col
        elif 'required?' in col_lower:
            col_map['required'] = col
        elif 'control type' in col_lower:
            col_map['type'] = col
        elif 'allowable range' in col_lower:
            col_map['options'] = col

    questions = []
    for index, row in df.iterrows():
        try:
            if 'question' in col_map and not pd.isna(row[col_map['question']]):
                q_text = str(row[col_map['question']]).strip()
                if q_text == '' or q_text == 'nan' or 'Q#' in q_text or 'Question & UI Label' in q_text:
                    continue

                req = False
                if 'required' in col_map and not pd.isna(row[col_map['required']]):
                    req_str = str(row[col_map['required']]).strip().lower()
                    req = 'yes' in req_str or 'required' in req_str

                q_type = 'text input'
                if 'type' in col_map and not pd.isna(row[col_map['type']]):
                    q_type = str(row[col_map['type']]).strip().lower()

                options = []
                if 'options' in col_map and not pd.isna(row[col_map['options']]):
                    opts_raw = str(row[col_map['options']])
                    if not any(t in q_type for t in ['text input', 'number input', 'email input', 'phone input', 'numeric']):
                        if '\n' in opts_raw:
                            options = [o.strip() for o in opts_raw.split('\n') if o.strip()]
                        else:
                            options = [opts_raw.strip()]
                        options = [re.sub(r'^[-•*]\s*', '', o) for o in options if o]
                        options = [o for o in options if not o.lower().startswith('none (')]

                questions.append({
                    'subsection': '',
                    'text': q_text,
                    'required': req,
                    'type': q_type,
                    'options': options
                })
        except:
            pass

    print(f"Found {len(questions)} pre-survey questions")
    return [{
        'title': 'Pre-Survey Details',
        'questions': questions
    }]

def get_consent_text(xls):
    print("\n--- Extracting Consent Text ---")
    df = pd.read_excel(xls, sheet_name='1_About the Study & Consent')

    # Text is usually in the first column, 5th and 8th rows
    consent_texts = []
    for index, row in df.iterrows():
        for col in df.columns:
            val = str(row[col]).strip()
            if 'we are conducting a survey' in val.lower() or 'हम <राज्य' in val.lower() or 'do you consent' in val.lower() or 'क्या आप इस सर्वे' in val.lower():
                consent_texts.append(val)
                break

    if consent_texts:
        return consent_texts

    return [
        "We are conducting a survey with individual households, Anganwadi Centres and other such institutions to map the current cooking practices, identify barriers and opportunities for shift to clean cooking fuels. The data collected during this survey will remain confidential, and will be used only for the purpose of this study.\n\nDo you consent to share your information with us for this survey? (No/Yes)",
        "नमस्ते, हम घरों, आंगनवाड़ी केंद्रों और ऐसी ही दूसरी संस्थाओं के साथ एक सर्वे कर रहे हैं। इसका मकसद खाना पकाने के मौजूदा तरीकों को समझना और साफ़-सुथरे कुकिंग फ़्यूल (ईंधन) को अपनाने में आने वाली रुकावटों और मौकों की पहचान करना है। इस सर्वे में इकट्ठा की गई जानकारी गोपनीय रहेगी और इसका इस्तेमाल सिर्फ़ इसी स्टडी के लिए किया जाएगा।\n\nक्या आप इस सर्वे के लिए हमारे साथ अपनी जानकारी शेयर करने के लिए सहमत हैं? (नहीं/हाँ)"
    ]

def main():
    excel_file = 'Clean_Cooking_Forms_Questions_and_Default_Answers.xlsx'
    xls = pd.ExcelFile(excel_file)

    pre_survey = parse_pre_survey(xls)
    consent = get_consent_text(xls)

    # Extract sections for each and prepend pre_survey
    household = pre_survey + extract_questions(xls, 'Revised -3.1_Household Cooking')
    anganwadi = pre_survey + extract_questions(xls, 'Revised 3.2_Cooking@Anganwadi C')
    school = pre_survey + extract_questions(xls, '3.3_Cooking@Schools with MDM')

    # Gram Panchayat Representative is in 3.4
    gram_panchayat = pre_survey + extract_questions(xls, '3.4_Gram Panchayat')

    data = {
        'consent': consent,
        'Household': household,
        'Anganwadi Centre': anganwadi,
        'School with Mid Day Meal Programme': school,
        'Gram Panchayat Representative': gram_panchayat
    }

    with open('form_data_grouped.json', 'w') as f:
        json.dump(data, f, indent=2)

    print("\nSaved form_data_grouped.json")

main()
