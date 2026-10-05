import pandas as pd
excel_file = 'Clean_Cooking_Forms_Questions_and_Default_Answers.xlsx'
xls = pd.ExcelFile(excel_file)
df = pd.read_excel(xls, sheet_name='Revised -3.1_Household Cooking')

header_idx = -1
for i in range(min(15, len(df))):
    row_vals = [str(x).lower() for x in df.iloc[i].values]
    if any('question' in v and 'label' in v for v in row_vals):
        header_idx = i + 1
        break

if header_idx != -1:
    df = pd.read_excel(xls, sheet_name='Revised -3.1_Household Cooking', header=header_idx)
else:
    df = pd.read_excel(xls, sheet_name='Revised -3.1_Household Cooking', header=1)

print("Sections found:")
for index, row in df.iterrows():
    try:
        q_val = str(row[df.columns[0]]).strip()
        if q_val.lower().startswith('section'):
            print(f"- {q_val}")
    except:
        pass
