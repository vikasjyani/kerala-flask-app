import pandas as pd
import json
import re

def clean_text(text):
    if pd.isna(text):
        return ""
    return str(text).strip()

def extract_questions(xls, sheet_name):
    print(f"--- Parsing {sheet_name} ---")
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
            # Handle potential section headers in Q# column
            q_val = str(row[df.columns[0]]).strip()
            if q_val.lower().startswith('section'):
                current_section = re.sub(r'^section\s*\d+\s*:\s*', '', q_val, flags=re.IGNORECASE)
                continue

            if 'question' in col_map and not pd.isna(row[col_map['question']]):
                q_text = str(row[col_map['question']]).strip()
                if q_text == '' or q_text == 'nan' or 'Q#' in q_text or 'Question & UI Label' in q_text:
                    continue

                # Skip instructional text
                if 'green denotes' in q_text.lower() or '--- denotes' in q_text.lower() or 'this form opens' in q_text.lower():
                    continue

                req = False
                if 'required' in col_map and not pd.isna(row[col_map['required']]):
                    req = str(row[col_map['required']]).strip().lower() == 'yes'

                q_type = 'text input'
                if 'type' in col_map and not pd.isna(row[col_map['type']]):
                    q_type = str(row[col_map['type']]).strip().lower()

                options = []
                if 'options' in col_map and not pd.isna(row[col_map['options']]):
                    opts_raw = str(row[col_map['options']])
                    if '\n' in opts_raw:
                        options = [o.strip() for o in opts_raw.split('\n') if o.strip()]
                    elif ',' in opts_raw:
                        options = [o.strip() for o in opts_raw.split(',') if o.strip()]
                    else:
                        options = [opts_raw.strip()]

                # Ensure options don't have leading/trailing weird chars
                options = [re.sub(r'^[-•*]\s*', '', o) for o in options if o]

                # Get category/section from the second column if available
                if len(df.columns) > 1 and not pd.isna(row[df.columns[1]]):
                    potential_section = str(row[df.columns[1]]).strip()
                    if potential_section and potential_section.lower() != 'nan':
                        current_section = potential_section

                if current_section not in sections_dict:
                    sections_dict[current_section] = []

                sections_dict[current_section].append({
                    'text': q_text,
                    'required': req,
                    'type': q_type,
                    'options': options
                })
        except Exception as e:
            print(f"Error on row {index}: {e}")

    # Convert to list of sections to maintain order (using dict maintains order in Python 3.7+)
    sections_list = []
    for section_name, questions in sections_dict.items():
        if questions: # Only add sections with questions
            sections_list.append({
                'title': section_name,
                'questions': questions
            })

    num_q = sum(len(s['questions']) for s in sections_list)
    print(f"Found {num_q} questions across {len(sections_list)} sections for {sheet_name}")
    return sections_list

def main():
    excel_file = 'Clean_Cooking_Forms_Questions_and_Default_Answers.xlsx'
    xls = pd.ExcelFile(excel_file)

    data = {
        'Household': extract_questions(xls, 'Revised -3.1_Household Cooking'),
        'Anganwadi Centre': extract_questions(xls, 'Revised 3.2_Cooking@Anganwadi C'),
        'School with Mid Day Meal Programme': extract_questions(xls, '3.3_Cooking@Schools with MDM'),
        # Gram Panchayat is empty in the excel file sheet '3.4_Gram Panchayat'
        'Gram Panchayat Representative': []
    }

    with open('form_data_grouped.json', 'w') as f:
        json.dump(data, f, indent=2)

main()
