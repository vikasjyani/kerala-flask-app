import json

def load_data():
    with open('form_data_grouped.json') as f:
        return json.load(f)

def generate_form_html(data):
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clean Cooking Survey</title>
    <!-- Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <!-- Bootstrap Icons -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">

    <style>
        :root {
            --brand-green: #004d40;
            --brand-soft: #e0f2f1;
            --brand: #00897b;
            --radius-lg: 12px;
            --shadow-sm: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075);
            --shadow-green: 0 4px 12px rgba(0, 77, 64, 0.08);
        }

        body {
            font-family: 'Poppins', sans-serif;
            background-color: #f8f9fa;
            color: #333;
            padding-bottom: 50px;
        }

        .header-container {
            background: white;
            box-shadow: var(--shadow-sm);
        }

        .top-bar {
            padding: 10px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .green-strip {
            background-color: var(--brand-green);
            padding: 10px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .page-title {
            color: var(--brand-green);
            font-weight: 700;
        }

        .card {
            border: none;
            border-radius: var(--radius-lg);
            box-shadow: var(--shadow-green);
            margin-bottom: 1.5rem;
        }

        .card-body {
            padding: 2rem;
        }

        .section-heading {
            color: var(--brand-green);
            font-weight: 600;
            font-size: 1.25rem;
            margin-bottom: 1.5rem;
            display: flex;
            align-items: center;
        }

        .form-label {
            font-weight: 500;
            color: #495057;
        }

        .form-control, .form-select {
            border-radius: 8px;
            padding: 0.75rem;
            border-color: #ced4da;
        }

        .form-control:focus, .form-select:focus {
            border-color: var(--brand);
            box-shadow: 0 0 0 0.25rem rgba(0, 137, 123, 0.25);
        }

        .btn-nav-next {
            background-color: var(--brand-green);
            color: white;
            border-radius: 8px;
            padding: 0.5rem 1.5rem;
            font-weight: 600;
        }

        .btn-nav-next:hover {
            background-color: #00332a;
            color: white;
        }

        .btn-nav-back {
            background-color: transparent;
            color: var(--brand-green);
            border: 1px solid var(--brand-green);
            border-radius: 8px;
            padding: 0.5rem 1.5rem;
            font-weight: 600;
        }

        .btn-nav-back:hover {
            background-color: var(--brand-soft);
            color: var(--brand-green);
        }

        .radio-card {
            border: 1px solid #ced4da;
            border-radius: 8px;
            padding: 10px 15px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.2s;
        }

        .radio-card:hover {
            background-color: var(--brand-soft);
            border-color: var(--brand);
        }

        .radio-card input[type="radio"] {
            margin-right: 10px;
        }

        .step-container {
            display: none;
        }

        .step-container.active {
            display: block;
            animation: fadeIn 0.3s ease-in-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .progress-indicator {
            font-size: 0.875rem;
            color: var(--brand);
            font-weight: 600;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
        }
    </style>
</head>
<body>

    <div class="header-container mb-4">
        <div class="green-strip">
            <div class="d-flex align-items-center">
                <span class="ms-2 text-white fw-bold fs-5">Clean Cooking Survey</span>
            </div>
        </div>
    </div>

    <div class="container my-4">
        <div class="row justify-content-center">
            <div class="col-lg-8">

                <div id="selection-screen" class="step-container active">
                    <div class="text-center mb-4">
                        <h1 class="page-title mb-2">Select Respondent Type</h1>
                        <p class="text-muted">Please choose the type of respondent for this survey.</p>
                    </div>

                    <div class="card shadow-green">
                        <div class="card-body">
                            <form id="respondent-type-form">
                                <div class="mb-4">
                                    <label class="form-label d-block mb-3">Nature of Respondent *</label>

                                    <label class="radio-card d-block">
                                        <input type="radio" name="respondent_type" value="Household" required>
                                        Household
                                    </label>

                                    <label class="radio-card d-block">
                                        <input type="radio" name="respondent_type" value="Anganwadi Centre">
                                        Anganwadi Centre
                                    </label>

                                    <label class="radio-card d-block">
                                        <input type="radio" name="respondent_type" value="School with Mid Day Meal Programme">
                                        School with Mid Day Meal Programme
                                    </label>

                                    <label class="radio-card d-block">
                                        <input type="radio" name="respondent_type" value="Gram Panchayat Representative">
                                        Gram Panchayat Representative
                                    </label>
                                </div>

                                <div class="d-flex justify-content-end">
                                    <button type="button" class="btn btn-nav-next" id="start-btn">Start Survey <i class="bi bi-arrow-right ms-2"></i></button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>

                <div id="survey-container" style="display: none;">
                    <div class="text-center mb-4">
                        <h1 class="page-title mb-2" id="survey-title">Survey</h1>
                    </div>

                    <div id="progress-wrapper" class="mb-4">
                        <div class="d-flex justify-content-between">
                            <span class="progress-indicator" id="step-indicator">Step 1 of X</span>
                        </div>
                        <div class="progress" style="height: 8px;">
                            <div class="progress-bar bg-success" id="progress-bar" role="progressbar" style="width: 0%;"></div>
                        </div>
                    </div>

                    <form id="main-survey-form">
                        <!-- Sections will be injected here -->
                    </form>
                </div>

            </div>
        </div>
    </div>

    <!-- Data embedded as JSON -->
    <script id="survey-data" type="application/json">
    '''

    html += json.dumps(data)

    html += '''
    </script>

    <script>
        const surveyData = JSON.parse(document.getElementById('survey-data').textContent);
        let currentType = '';
        let currentSectionIndex = 0;
        let sections = [];

        document.getElementById('start-btn').addEventListener('click', function() {
            const selected = document.querySelector('input[name="respondent_type"]:checked');
            if (!selected) {
                alert('Please select a respondent type');
                return;
            }

            currentType = selected.value;
            sections = surveyData[currentType] || [];

            if (sections.length === 0) {
                alert('No questions available for this respondent type yet.');
                return;
            }

            currentSectionIndex = 0;

            document.getElementById('selection-screen').classList.remove('active');
            document.getElementById('survey-container').style.display = 'block';
            document.getElementById('survey-title').textContent = currentType + ' Survey';

            renderCurrentSection();
        });

        function renderCurrentSection() {
            const form = document.getElementById('main-survey-form');
            form.innerHTML = '';

            if (currentSectionIndex >= sections.length) {
                // Completed
                form.innerHTML = `
                    <div class="card text-center py-5">
                        <div class="card-body">
                            <i class="bi bi-check-circle-fill text-success" style="font-size: 4rem;"></i>
                            <h2 class="mt-3 text-success">Survey Completed!</h2>
                            <p class="text-muted">Thank you for providing the information.</p>
                            <button type="button" class="btn btn-nav-back mt-3" onclick="location.reload()">Back to Start</button>
                        </div>
                    </div>
                `;
                document.getElementById('progress-wrapper').style.display = 'none';
                return;
            }

            const section = sections[currentSectionIndex];

            // Update progress
            const progressPct = ((currentSectionIndex + 1) / sections.length) * 100;
            document.getElementById('step-indicator').textContent = `Section ${currentSectionIndex + 1} of ${sections.length}: ${section.title}`;
            document.getElementById('progress-bar').style.width = `${progressPct}%`;

            // Create card for section
            const card = document.createElement('div');
            card.className = 'card shadow-green step-container active';

            let cardBody = `
                <div class="card-body">
                    <h2 class="section-heading"><i class="bi bi-card-list me-2"></i>${section.title}</h2>
                    <div class="row g-4">
            `;

            // Add questions
            section.questions.forEach((q, idx) => {
                const reqStar = q.required ? '<span class="text-danger">*</span>' : '';
                const qId = `q_${currentSectionIndex}_${idx}`;

                cardBody += `<div class="col-12"><div class="mb-3">`;
                cardBody += `<label class="form-label fw-bold">${q.text} ${reqStar}</label>`;

                // Render based on type and options
                const typeLower = q.type ? q.type.toLowerCase() : '';

                if (q.options && q.options.length > 0) {
                    if (typeLower.includes('dropdown') || q.options.length > 5) {
                        cardBody += `<select class="form-select" name="${qId}" ${q.required ? 'required' : ''}>`;
                        cardBody += `<option value="">Select an option</option>`;
                        q.options.forEach(opt => {
                            if (opt && opt.trim() !== 'None (\'Select an option\' prompt)' && opt.trim() !== 'None (\'Select District\' prompt)') {
                                cardBody += `<option value="${opt.replace(/"/g, '&quot;')}">${opt}</option>`;
                            }
                        });
                        cardBody += `</select>`;
                    } else {
                        // Radio buttons
                        cardBody += `<div class="mt-2">`;
                        q.options.forEach((opt, oIdx) => {
                             if (opt && opt.trim() !== 'None (\'Select an option\' prompt)') {
                                cardBody += `
                                <div class="form-check mb-2">
                                    <input class="form-check-input" type="radio" name="${qId}" id="${qId}_${oIdx}" value="${opt.replace(/"/g, '&quot;')}" ${q.required ? 'required' : ''}>
                                    <label class="form-check-label" for="${qId}_${oIdx}">${opt}</label>
                                </div>`;
                            }
                        });
                        cardBody += `</div>`;
                    }
                } else if (typeLower.includes('number') || typeLower.includes('numeric')) {
                    cardBody += `<input type="number" class="form-control" name="${qId}" ${q.required ? 'required' : ''}>`;
                } else {
                    cardBody += `<input type="text" class="form-control" name="${qId}" ${q.required ? 'required' : ''}>`;
                }

                cardBody += `</div></div>`;
            });

            cardBody += `</div></div>`;
            card.innerHTML = cardBody;
            form.appendChild(card);

            // Navigation buttons
            const navDiv = document.createElement('div');
            navDiv.className = 'd-flex justify-content-between mt-4 mb-2';

            let btnHTML = '';
            if (currentSectionIndex > 0) {
                btnHTML += `<button type="button" class="btn btn-nav-back" onclick="prevSection()"><i class="bi bi-arrow-left me-2"></i>Back</button>`;
            } else {
                btnHTML += `<button type="button" class="btn btn-nav-back" onclick="location.reload()"><i class="bi bi-arrow-left me-2"></i>Back</button>`;
            }

            btnHTML += `<button type="button" class="btn btn-nav-next ms-auto" onclick="nextSection()">${currentSectionIndex === sections.length - 1 ? 'Submit' : 'Next'} <i class="bi bi-arrow-right ms-2"></i></button>`;

            navDiv.innerHTML = btnHTML;
            form.appendChild(navDiv);

            // Scroll to top
            window.scrollTo(0, 0);
        }

        window.nextSection = function() {
            // Basic validation
            const form = document.getElementById('main-survey-form');
            if (false && !form.reportValidity()) {
                return;
            }

            currentSectionIndex++;
            renderCurrentSection();
        };

        window.prevSection = function() {
            currentSectionIndex--;
            renderCurrentSection();
        };
    </script>
</body>
</html>'''

    with open('clean_cooking_forms.html', 'w') as f:
        f.write(html)

    print("Generated clean_cooking_forms.html")

data = load_data()
generate_form_html(data)
