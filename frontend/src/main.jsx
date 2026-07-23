import React, { useEffect, useMemo, useState } from 'react';
import { Joyride, STATUS } from 'react-joyride';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileText,
  Globe2,
  HeartPulse,
  Loader2,
  LogOut,
  LockKeyhole,
  Sparkles,
  Stethoscope,
  UserRound,
  ShieldCheck,
  UploadCloud,
  Download,
} from 'lucide-react';
import {
  clearAuthToken,
  extractText,
  getAuthToken,
  getMe,
  getPatientView,
  getReport,
  getReportSafetyAudits,
  listReports,
  loginUser,
  logoutUser,
  parseReport,
  registerUser,
  seedKnowledgeBase,
  uploadReport,
} from './services/api';
import './styles.css';

const riskMeta = {
  green: { label: 'Green', className: 'risk-green', text: 'Mostly within range' },
  yellow: { label: 'Yellow', className: 'risk-yellow', text: 'Routine doctor discussion' },
  orange: { label: 'Orange', className: 'risk-orange', text: 'Consult doctor soon' },
  red: { label: 'Red', className: 'risk-red', text: 'Seek medical care quickly' },
  unknown: { label: 'Unknown', className: 'risk-unknown', text: 'Not enough information yet' },
};

const statusMeta = {
  low: 'status-low',
  high: 'status-high',
  borderline: 'status-borderline',
  normal: 'status-normal',
  unknown: 'status-unknown',
};

function normalizeReportFromUpload(payload) {
  return payload?.report || payload;
}

function StepRow({ label, state }) {
  const icon = state === 'done'
    ? <CheckCircle2 size={18} />
    : state === 'running'
      ? <Loader2 className="spin" size={18} />
      : <span className="step-dot" />;

  return (
    <div className={`step-row ${state}`}>
      {icon}
      <span>{label}</span>
    </div>
  );
}

function Header({ onStartTour, authUser, onLogout }) {
  return (
    <header className="app-header">
      <div className="brand-block">
        <div className="brand-icon"><HeartPulse size={28} /></div>
        <div>
          <h1>MedSenseAI</h1>
          <p>Safe medical report understanding assistant</p>
        </div>
      </div>
      <div className="header-badges">
        <span><ShieldCheck size={16} /> No diagnosis</span>
        <span><BookOpen size={16} /> RAG grounded</span>
        <span><Globe2 size={16} /> English / Hindi</span>
      </div>
      <div className="auth-header-actions">
        <span className="user-pill">
          <UserRound size={16} />
          {authUser?.username || 'User'}
        </span>
        <button className="tour-button" type="button" onClick={onStartTour}>
          Start guided tour
        </button>
        <button className="logout-button" type="button" onClick={onLogout}>
          <LogOut size={16} />
          Logout
        </button>
      </div>
    </header>
  );
}

function UploadPanel({ onPipelineComplete }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('Ready to process PDF, image, or scanned report.');
  const [error, setError] = useState('');
  const [steps, setSteps] = useState({ seed: 'idle', upload: 'idle', extract: 'idle', parse: 'idle', load: 'idle' });

  async function runPipeline() {
    if (!file) {
      setError('Select a report file first.');
      return;
    }

    setLoading(true);
    setError('');
    setMessage('Starting MedSenseAI report pipeline...');
    setSteps({ seed: 'running', upload: 'idle', extract: 'idle', parse: 'idle', load: 'idle' });

    try {
      await seedKnowledgeBase();
      setSteps((prev) => ({ ...prev, seed: 'done', upload: 'running' }));
      setMessage('Trusted medical knowledge base is ready. Uploading report...');

      const uploadPayload = await uploadReport(file);
      const uploadedReport = normalizeReportFromUpload(uploadPayload);
      const reportId = uploadedReport.id;
      setSteps((prev) => ({ ...prev, upload: 'done', extract: 'running' }));
      setMessage(`Report uploaded. Extracting text from report #${reportId}...`);

      await extractText(reportId);
      setSteps((prev) => ({ ...prev, extract: 'done', parse: 'running' }));
      setMessage('Text extracted. Parsing report and generating safe explanation...');

      await parseReport(reportId);
      setSteps((prev) => ({ ...prev, parse: 'done', load: 'running' }));
      setMessage('Report parsed. Loading final patient-friendly output...');

      const [report, patientView, audits] = await Promise.all([
        getReport(reportId),
        getPatientView(reportId, 'en'),
        getReportSafetyAudits(reportId),
      ]);
      setSteps((prev) => ({ ...prev, load: 'done' }));
      setMessage('Processing completed successfully.');
      onPipelineComplete({ report, patientView, audits });
    } catch (err) {
      setError(err?.data ? JSON.stringify(err.data, null, 2) : err.message);
      setMessage('Pipeline stopped. Check the error below.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="card upload-card" data-tour="upload">
      <div className="card-title-row">
        <div>
          <h2>Upload report</h2>
          <p>Upload CBC PDF, scanned PDF, JPG, PNG, or report image.</p>
        </div>
        <UploadCloud size={30} />
      </div>

      <label className="drop-zone">
        <input
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff"
          onChange={(event) => setFile(event.target.files?.[0] || null)}
        />
        <FileText size={36} />
        <strong>{file ? file.name : 'Choose medical report file'}</strong>
        <span>PDF/image reports supported. The app explains reports, not diagnoses disease.</span>
      </label>

      <button className="primary-button" disabled={loading || !file} onClick={runPipeline}>
        {loading ? <Loader2 className="spin" size={18} /> : <Activity size={18} />}
        Process report safely
      </button>

      <div className="steps-box" data-tour="pipeline">
        <StepRow label="Seed trusted medical knowledge" state={steps.seed} />
        <StepRow label="Upload report file" state={steps.upload} />
        <StepRow label="Extract text / OCR" state={steps.extract} />
        <StepRow label="Parse values + RAG explanation" state={steps.parse} />
        <StepRow label="Load patient view + safety audit" state={steps.load} />
      </div>

      <p className="helper-message">{message}</p>
      {error && <pre className="error-box">{error}</pre>}
    </section>
  );
}


function RiskMeter({ riskLevel }) {
  const levels = [
    { key: 'green', label: 'Green' },
    { key: 'yellow', label: 'Yellow' },
    { key: 'orange', label: 'Orange' },
    { key: 'red', label: 'Red' },
  ];
  const activeIndex = levels.findIndex((level) => level.key === riskLevel);

  return (
    <div className="risk-meter" data-current-risk={riskLevel || 'unknown'}>
      {levels.map((level, index) => (
        <div
          className={`risk-step ${level.key} ${index <= activeIndex ? 'active' : ''} ${index === activeIndex ? 'current' : ''}`}
          key={level.key}
        >
          <span />
          <strong>{level.label}</strong>
        </div>
      ))}
    </div>
  );
}


function getNeedsAttentionTests(report) {
  return (report?.test_results || []).filter((test) =>
    ['low', 'high', 'borderline'].includes(test.status)
  );
}

function getUniqueSources(report) {
  const sources = [];
  const seen = new Set();

  (report?.test_results || []).forEach((test) => {
    (test.explanation_sources || []).forEach((source) => {
      const key = `${source.source_name || ''}-${source.title || ''}-${source.source_url || ''}`;

      if (!seen.has(key)) {
        seen.add(key);
        sources.push(source);
      }
    });
  });

  return sources;
}

function getDoctorQuestions(report) {
  const questions = [];

  (report?.test_results || []).forEach((test) => {
    (test.doctor_questions || []).forEach((question) => {
      questions.push({
        testName: test.test_name,
        question,
      });
    });
  });

  return questions;
}

function PrintableSummary({ report, patientView, audits }) {
  if (!report) {
    return null;
  }

  const risk = riskMeta[report.overall_risk_level] || riskMeta.unknown;
  const latestAudit = audits?.[audits.length - 1];
  const attentionTests = getNeedsAttentionTests(report);
  const sources = getUniqueSources(report);
  const doctorQuestions = getDoctorQuestions(report);

  return (
    <section className="print-summary-sheet" aria-label="Printable patient summary">
      <div className="print-header">
        <div>
          <h1>MedSenseAI Patient Summary</h1>
          <p>Safe medical report understanding assistant</p>
        </div>
        <div className="print-risk-box">
          <span>Risk level</span>
          <strong>{risk.label}</strong>
        </div>
      </div>

      <div className="print-disclaimer">
        MedSenseAI explains medical reports in simple language. It does not diagnose disease,
        prescribe medicine, suggest dosage, or replace a qualified doctor.
      </div>

      <div className="print-meta-grid">
        <div><span>Report type</span><strong>{report.report_type || 'Medical Report'}</strong></div>
        <div><span>File</span><strong>{report.original_filename || 'Uploaded report'}</strong></div>
        <div><span>Age</span><strong>{report.patient_age || patientView?.patient_age || 'Not found'}</strong></div>
        <div><span>Gender</span><strong>{report.patient_gender || patientView?.patient_gender || 'Not found'}</strong></div>
        <div><span>Status</span><strong>{report.status || 'Unknown'}</strong></div>
        <div><span>Safety audit</span><strong>{latestAudit?.final_safety_status || 'Not available'}</strong></div>
      </div>

      <section className="print-section">
        <h2>Patient-friendly summary</h2>
        <p>{patientView?.summary || report.ai_summary || 'Summary not available.'}</p>
      </section>

      <section className="print-section">
        <h2>Values needing attention</h2>
        {attentionTests.length ? (
          <table className="print-table">
            <thead>
              <tr>
                <th>Test</th>
                <th>Value</th>
                <th>Reference range</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {attentionTests.map((test) => (
                <tr key={test.id || test.test_name}>
                  <td>{test.test_name}</td>
                  <td>{test.value} {test.unit}</td>
                  <td>{test.reference_range || 'Not found'}</td>
                  <td>{test.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No abnormal or borderline values were detected from the parsed report.</p>
        )}
      </section>

      <section className="print-section">
        <h2>All parsed tests</h2>
        <table className="print-table">
          <thead>
            <tr>
              <th>Test</th>
              <th>Value</th>
              <th>Reference range</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(report.test_results || []).map((test) => (
              <tr key={test.id || test.test_name}>
                <td>{test.test_name}</td>
                <td>{test.value} {test.unit}</td>
                <td>{test.reference_range || 'Not found'}</td>
                <td>{test.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {!!doctorQuestions.length && (
        <section className="print-section">
          <h2>Questions to ask the doctor</h2>
          <ul className="print-list">
            {doctorQuestions.slice(0, 12).map((item, index) => (
              <li key={`${item.testName}-${index}`}>
                <strong>{item.testName}:</strong> {item.question}
              </li>
            ))}
          </ul>
        </section>
      )}

      {!!sources.length && (
        <section className="print-section">
          <h2>Trusted sources used</h2>
          <ul className="print-list">
            {sources.slice(0, 12).map((source, index) => (
              <li key={`${source.title}-${index}`}>
                <strong>{source.source_name}</strong> — {source.title}
                {source.source_url ? <span> ({source.source_url})</span> : null}
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="print-footer">
        Generated by MedSenseAI. Bring this summary and the original report when consulting a qualified doctor.
      </div>
    </section>
  );
}


function SummaryPanel({ report, patientView, audits, onLanguageChange, onPrintSummary }) {
  if (!report) {
    return (
      <section className="card empty-state" data-tour="summary">
        <ShieldCheck size={46} />
        <h2>No report processed yet</h2>
        <p>Upload a report to see extracted tests, risk level, RAG explanations, doctor questions, and safety audit.</p>
      </section>
    );
  }

  const risk = riskMeta[report.overall_risk_level] || riskMeta.unknown;
  const latestAudit = audits?.[audits.length - 1];

  return (
    <section className="summary-grid">
      <div className="card summary-card" data-tour="summary">
        <div className="card-title-row">
          <div>
            <h2>{report.report_type || 'Medical Report'}</h2>
            <p>{report.original_filename}</p>
          </div>
          <span className={`risk-pill ${risk.className}`}>{risk.label}</span>
        </div>
        <div className="summary-meta">
          <div><span>Age</span><strong>{report.patient_age || patientView?.patient_age || 'Not found'}</strong></div>
          <div><span>Gender</span><strong>{report.patient_gender || patientView?.patient_gender || 'Not found'}</strong></div>
          <div><span>Status</span><strong>{report.status}</strong></div>
          <div><span>Risk meaning</span><strong>{risk.text}</strong></div>
          <div><span>Parser</span><strong>{report.parser_mode || 'not shown'}</strong></div>
        </div>
        <p className="summary-text">{patientView?.summary || report.ai_summary}</p>
        {report?.parser_message && (
          <p className="parser-note">{report.parser_message}</p>
        )}
        {report?.error_message && (
          <p className="parser-note error-note">{report.error_message}</p>
        )}
        <div className="language-row">
          <button onClick={() => onLanguageChange('en')}>English view</button>
          <button onClick={() => onLanguageChange('hi')}>Hindi view</button>
          <button className="export-button" type="button" onClick={onPrintSummary}>
            <Download size={16} />
            Print / Save PDF
          </button>
        </div>
      </div>

      <div className="card safety-card" data-tour="safety">
        <div className="card-title-row">
          <div>
            <h2>Safety audit</h2>
            <p>Checks diagnosis, treatment, dosage, and false reassurance patterns.</p>
          </div>
          <ShieldCheck size={28} />
        </div>
        <div className="audit-status">
          <strong>{latestAudit?.final_safety_status || 'Not available'}</strong>
          <span>Final safety status</span>
        </div>
        <ul className="audit-list">
          <li>Diagnosis claims blocked: {latestAudit?.blocked_diagnosis_claims?.length || 0}</li>
          <li>Treatment advice blocked: {latestAudit?.blocked_treatment_advice?.length || 0}</li>
          <li>False reassurance blocked: {latestAudit?.blocked_false_reassurance?.length || 0}</li>
        </ul>
      </div>
    </section>
  );
}
function NeedsAttentionPanel({ report }) {
  const tests = (report?.test_results || []).filter((test) =>
    ['low', 'high', 'borderline'].includes(test.status)
  );

  if (!tests.length) {
    return null;
  }

  return (
    <section className="card attention-card" data-tour="attention">
      <div className="card-title-row">
        <div>
          <h2>Needs attention</h2>
          <p>Abnormal or borderline values found in this report.</p>
        </div>
        <AlertTriangle size={28} />
      </div>

      <div className="attention-list">
        {tests.map((test) => (
          <div className="attention-item" key={test.id || test.test_name}>
            <div>
              <strong>{test.test_name}</strong>
              <span>
                {test.value} {test.unit} · Reference: {test.reference_range || 'Not found'}
              </span>
            </div>
            <span className={`status-pill ${statusMeta[test.status] || 'status-unknown'}`}>
              {test.status}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
function getShortText(text, limit = 180) {
  if (!text) {
    return 'Explanation will appear here after parsing.';
  }

  if (text.length <= limit) {
    return text;
  }

  return `${text.slice(0, limit).trim()}...`;
}

function TestStatusIcon({ status }) {
  if (['low', 'high', 'borderline'].includes(status)) {
    return <AlertTriangle size={18} />;
  }

  if (status === 'normal') {
    return <CheckCircle2 size={18} />;
  }

  return <Activity size={18} />;
}

function TestResults({ report }) {
  const [viewMode, setViewMode] = useState('patient');
  const tests = report?.test_results || [];

  if (!tests.length) {
    return null;
  }

  return (
    <section className="card test-results-card interactive-card" data-tour="test-results">
      <div className="card-title-row">
        <div>
          <span className="section-kicker">Structured extraction</span>
          <h2>Interactive test results</h2>
          <p>Compact cards first. Open each test for explanation, sources, and doctor questions.</p>
        </div>
        <Activity size={28} />
      </div>

      <div className="test-toolbar">
        <div>
          <strong>{tests.length}</strong>
          <span>parsed values</span>
        </div>
        <div className="view-toggle">
          <button
            className={viewMode === 'patient' ? 'active' : ''}
            type="button"
            onClick={() => setViewMode('patient')}
          >
            Patient mode
          </button>
          <button
            className={viewMode === 'technical' ? 'active' : ''}
            type="button"
            onClick={() => setViewMode('technical')}
          >
            Technical mode
          </button>
        </div>
      </div>

      <div className="test-list compact-test-list">
        {tests.map((test, index) => (
          <article
            className={`test-card compact-test-card status-${test.status || 'unknown'}-card`}
            key={test.id || `${test.test_name}-${index}`}
          >
            <div className="test-card-top">
              <div className={`status-icon status-${test.status || 'unknown'}-icon`}>
                <TestStatusIcon status={test.status} />
              </div>

              <div className="test-primary">
                <h3>{test.test_name}</h3>
                <p>{test.reference_range ? `Reference: ${test.reference_range}` : 'Reference range not found'}</p>
              </div>

              <div className="test-value-block">
                <strong>{test.value} {test.unit}</strong>
                <span className={`status-pill ${statusMeta[test.status] || 'status-unknown'}`}>{test.status}</span>
              </div>
            </div>

            <div className="test-metrics">
              <span><b>Value</b>{test.value || '—'} {test.unit || ''}</span>
              <span><b>Range</b>{test.reference_range || '—'}</span>
              <span><b>Flag</b>{test.flag || test.status || '—'}</span>
            </div>

            {viewMode === 'patient' ? (
              <p className="test-preview">{getShortText(test.simple_explanation)}</p>
            ) : (
              <div className="technical-preview">
                <span>Unit: <strong>{test.unit || 'Not found'}</strong></span>
                <span>Reference: <strong>{test.reference_range || 'Not found'}</strong></span>
                <span>Status: <strong>{test.status || 'unknown'}</strong></span>
              </div>
            )}

            <details className="test-more">
              <summary>View full details</summary>

              <div className="test-expanded">
                <p className="explanation-text">{test.simple_explanation}</p>

                {!!test.explanation_sources?.length && (
                  <div className="sources-block">
                    <strong>Sources</strong>
                    {test.explanation_sources.map((source, sourceIndex) => (
                      <a href={source.source_url} target="_blank" rel="noreferrer" key={`${source.title}-${sourceIndex}`}>
                        {source.source_name}: {source.title}
                      </a>
                    ))}
                  </div>
                )}

                {!!test.doctor_questions?.length && (
                  <details className="questions-block">
                    <summary>Doctor questions</summary>
                    <ul>
                      {test.doctor_questions.map((question, questionIndex) => <li key={questionIndex}>{question}</li>)}
                    </ul>
                  </details>
                )}
              </div>
            </details>
          </article>
        ))}
      </div>
    </section>
  );
}


function PatientViewPanel({ patientView }) {
  if (!patientView) {
    return null;
  }

  return (
    <section className="card patient-view-card" data-tour="patient-view">
      <div className="card-title-row">
        <div>
          <h2>Patient-friendly view</h2>
          <p>Language: {patientView.language === 'hi' ? 'Hindi' : 'English'}</p>
        </div>
        <Globe2 size={28} />
      </div>
      <p>{patientView.summary}</p>
      <div className="patient-tests">
        {(patientView.tests || []).slice(0, 5).map((test, index) => (
          <div key={`${test.test_name}-${index}`}>
            <strong>{test.test_name}</strong>
            <span>{test.value} {test.unit} · {test.status_hindi || test.status}</span>
            <p>{test.explanation}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
function ExtractedTextPanel({ report }) {
  if (!report?.extracted_text) {
    return null;
  }

  return (
    <section className="card ocr-card" data-tour="ocr-text">
      <div className="card-title-row">
        <div>
          <h2>Extracted OCR text</h2>
          <p>Useful for debugging scanned reports and image reports.</p>
        </div>
        <FileText size={28} />
      </div>

      <details>
        <summary>View extracted text</summary>
        <pre className="ocr-text">{report.extracted_text}</pre>
      </details>
    </section>
  );
} 
function HistoryPanel({ onSelectReport, refreshKey }) {
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const data = await listReports();
      setReports(Array.isArray(data) ? data.slice().reverse() : []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [refreshKey]);

  return (
    <section className="card history-card" data-tour="history">
      <div className="card-title-row">
        <div>
          <h2>Report history</h2>
          <p>Load an earlier processed report.</p>
        </div>
        <button className="secondary-button" onClick={refresh}>{loading ? 'Loading...' : 'Refresh'}</button>
      </div>
      <div className="history-list">
        {reports.slice(0, 8).map((report) => {
          const risk = riskMeta[report.overall_risk_level] || riskMeta.unknown;
          return (
            <button key={report.id} onClick={() => onSelectReport(report.id)}>
              <span>#{report.id} {report.original_filename || 'Report'}</span>
              <small>{report.report_type || 'Unparsed'} · <b className={risk.className}>{risk.label}</b></small>
            </button>
          );
        })}
        {!reports.length && <p className="muted">No report history yet.</p>}
      </div>
    </section>
  );
}


function ProductFeatureCard({ icon, title, text }) {
  return (
    <article className="product-feature-card">
      <div className="product-feature-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}

function ProductWorkflow() {
  const steps = [
    'Upload',
    'OCR',
    'Parse',
    'RAG Explain',
    'Safety Audit',
  ];

  return (
    <div className="product-workflow">
      {steps.map((step, index) => (
        <div className="product-workflow-step" key={step}>
          <span>{index + 1}</span>
          <strong>{step}</strong>
        </div>
      ))}
    </div>
  );
}

function PublicProductPanel() {
  return (
    <section className="product-landing-panel minimal-product-panel">
      <div className="minimal-hero-card">
        <span className="eyebrow">Safe AI medical report understanding</span>
        <h2>Understand lab reports safely, without medical guesswork.</h2>
        <p>
          Upload a report, extract values, get simple explanations, doctor questions,
          and a safety-checked summary in English or Hindi.
        </p>

        <div className="minimal-trust-row">
          <span><ShieldCheck size={16} /> No diagnosis</span>
          <span><BookOpen size={16} /> RAG grounded</span>
          <span><LockKeyhole size={16} /> Private history</span>
        </div>
      </div>

      <div className="minimal-flow-card">
        <span>Upload</span>
        <i />
        <span>OCR</span>
        <i />
        <span>Explain</span>
        <i />
        <span>Safety audit</span>
      </div>

      <p className="minimal-footnote">
        MedSenseAI does not prescribe, diagnose, or replace a qualified doctor.
      </p>
    </section>
  );
}

function DashboardProductStrip() {
  return (
    <section className="product-strip" aria-label="MedSenseAI product overview">
      <div>
        <Sparkles size={20} />
        <span>AI-assisted report explanation</span>
      </div>
      <div>
        <Stethoscope size={20} />
        <span>Doctor-question generator</span>
      </div>
      <div>
        <BookOpen size={20} />
        <span>Trusted source context</span>
      </div>
      <div>
        <ShieldCheck size={20} />
        <span>Safety audit before output</span>
      </div>
    </section>
  );
}


function AuthScreen({ onAuthSuccess }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showCredentials, setShowCredentials] = useState(false);

  const isRegister = mode === 'register';

  function updateField(field, value) {
    setForm((previous) => ({ ...previous, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError('');

    try {
      const payload = {
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
      };

      const data = isRegister
        ? await registerUser(payload)
        : await loginUser({ username: payload.username, password: payload.password });

      setForm({
        username: '',
        email: '',
        password: '',
      });

      onAuthSuccess(data.user);
    } catch (err) {
      setError(err?.data ? JSON.stringify(err.data, null, 2) : err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell auth-shell product-auth-shell">
      <PublicProductPanel />

      <section className="auth-card product-auth-card">
        <div className="brand-block auth-brand">
          <div className="brand-icon"><HeartPulse size={28} /></div>
          <div>
            <h1>MedSenseAI</h1>
            <p>Sign in to keep your medical reports private.</p>
          </div>
        </div>

        <div className="auth-mode-tabs">
          <button
            type="button"
            className={!isRegister ? 'active' : ''}
            onClick={() => {
              setMode('login');
              setError('');
            }}
          >
            Login
          </button>
          <button
            type="button"
            className={isRegister ? 'active' : ''}
            onClick={() => {
              setMode('register');
              setError('');
            }}
          >
            Register
          </button>
        </div>

        <div className="compact-social-row" aria-label="Social sign-in options">
          <button type="button" className="social-mini-button google" disabled title="Google sign-in coming soon">
            <span>G</span>
            Google
          </button>
          <button type="button" className="social-mini-button apple" disabled title="Apple sign-in coming soon">
            <span></span>
            Apple
          </button>
          <button type="button" className="social-mini-button facebook" disabled title="Facebook sign-in coming soon">
            <span>f</span>
            Facebook
          </button>
        </div>

        <div className="auth-divider compact-divider">
          <span>or</span>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} autoComplete="off">
          <div className="auth-privacy-row">
            <span>Credential privacy mode</span>
            <button type="button" onClick={() => setShowCredentials((value) => !value)}>
              {showCredentials ? 'Hide credentials' : 'Show while typing'}
            </button>
          </div>

          <label>
            <span>Username</span>
            <input
              type={showCredentials ? 'text' : 'password'}
              className={!showCredentials ? 'secure-input' : ''}
              value={form.username}
              onChange={(event) => updateField('username', event.target.value)}
              placeholder="Enter username"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck="false"
            />
          </label>

          {isRegister && (
            <label>
              <span>Email optional</span>
              <input
                type={showCredentials ? 'email' : 'password'}
                className={!showCredentials ? 'secure-input' : ''}
                value={form.email}
                onChange={(event) => updateField('email', event.target.value)}
                placeholder="Enter email"
                autoComplete="off"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck="false"
              />
            </label>
          )}

          <label>
            <span>Password</span>
            <input
              type={showCredentials ? 'text' : 'password'}
              className={!showCredentials ? 'secure-input' : ''}
              value={form.password}
              onChange={(event) => updateField('password', event.target.value)}
              placeholder="Enter password"
              autoComplete="new-password"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck="false"
            />
          </label>

          <button className="primary-button" disabled={loading} type="submit">
            {loading ? <Loader2 className="spin" size={18} /> : <ShieldCheck size={18} />}
            {isRegister ? 'Create account' : 'Login'}
          </button>

          {error && <pre className="error-box">{error}</pre>}
        </form>

        <p className="auth-note">
          Your report history is linked to your account. This is still a demo app, so avoid uploading highly sensitive real patient data.
        </p>
      </section>
    </main>
  );
}

function App() {
  const [authUser, setAuthUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [report, setReport] = useState(null);
  const [patientView, setPatientView] = useState(null);
  const [audits, setAudits] = useState([]);
  const [globalError, setGlobalError] = useState('');
  const [runTour, setRunTour] = useState(false);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const abnormalCount = useMemo(() => {
    return (report?.test_results || []).filter((test) => ['low', 'high', 'borderline'].includes(test.status)).length;
  }, [report]);

  useEffect(() => {
    async function restoreSession() {
      if (!getAuthToken()) {
        setAuthLoading(false);
        return;
      }

      try {
        const data = await getMe();
        setAuthUser(data.user);
      } catch {
        clearAuthToken();
        setAuthUser(null);
      } finally {
        setAuthLoading(false);
      }
    }

    restoreSession();
  }, []);

  async function loadReport(reportId, language = 'en') {
    try {
      setGlobalError('');
      const [detail, view, auditData] = await Promise.all([
        getReport(reportId),
        getPatientView(reportId, language),
        getReportSafetyAudits(reportId),
      ]);
      setReport(detail);
      setPatientView(view);
      setAudits(auditData);
    } catch (error) {
      setGlobalError(error.message);
    }
  }

  async function changeLanguage(language) {
    if (!report?.id) return;
    try {
      const view = await getPatientView(report.id, language);
      setPatientView(view);
    } catch (error) {
      setGlobalError(error.message);
    }
  }

  function handlePipelineComplete(data) {
    setReport(data.report);
    setPatientView(data.patientView);
    setAudits(data.audits || []);
    setHistoryRefreshKey((value) => value + 1);
  }

  function handleAuthSuccess(user) {
    setAuthUser(user);
    setReport(null);
    setPatientView(null);
    setAudits([]);
    setHistoryRefreshKey((value) => value + 1);
  }

  async function handleLogout() {
    try {
      await logoutUser();
    } catch {
      clearAuthToken();
    }

    setAuthUser(null);
    setReport(null);
    setPatientView(null);
    setAudits([]);
  }

  function handlePrintSummary() {
    if (!report) {
      return;
    }

    const previousTitle = document.title;
    document.title = `MedSenseAI-summary-${report.id || 'report'}`;
    document.body.classList.add('printing-summary');

    window.setTimeout(() => {
      window.print();
      document.body.classList.remove('printing-summary');
      window.setTimeout(() => {
        document.title = previousTitle;
      }, 300);
    }, 80);
  }

  function handleJoyrideCallback(data) {
    const { status } = data;

    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) {
      setRunTour(false);
    }
  }

  const tourSteps = [
    {
      target: '[data-tour="upload"]',
      content: 'Start here by uploading a PDF, scanned report, JPG, PNG, or medical report image.',
      disableBeacon: true,
    },
    {
      target: '[data-tour="pipeline"]',
      content: 'This shows the full MedSenseAI pipeline: knowledge base, upload, OCR/text extraction, parsing, RAG explanation, and safety audit.',
    },
    {
      target: '[data-tour="stats"]',
      content: 'These cards summarize how many tests were parsed, how many need attention, and whether the safety audit passed.',
    },
    {
      target: '[data-tour="summary"]',
      content: 'This area shows the detected report type, patient details, risk level, parser mode, and patient-friendly summary.',
    },
    {
      target: '[data-tour="safety"]',
      content: 'The safety audit checks that the app does not diagnose disease, prescribe medicine, suggest dosage, or falsely reassure users.',
    },
    {
      target: '[data-tour="attention"]',
      content: 'After processing, abnormal or borderline values appear here first so the user knows what to discuss with a doctor.',
    },
    {
      target: '[data-tour="patient-view"]',
      content: 'This section converts technical report language into simple patient-friendly English or Hindi explanations.',
    },
    {
      target: '[data-tour="test-results"]',
      content: 'Each parsed test shows value, unit, reference range, status, explanation, trusted sources, and doctor questions.',
    },
    {
      target: '[data-tour="ocr-text"]',
      content: 'The extracted OCR text helps debug scanned reports and understand what the parser received.',
    },
    {
      target: '[data-tour="history"]',
      content: 'Previously uploaded reports can be loaded again from here.',
    },
  ];

  if (authLoading) {
    return (
      <main className="app-shell auth-shell">
        <section className="auth-card loading-auth-card">
          <Loader2 className="spin" size={28} />
          <h2>Loading MedSenseAI...</h2>
        </section>
      </main>
    );
  }

  if (!authUser) {
    return <AuthScreen onAuthSuccess={handleAuthSuccess} />;
  }

  return (
    <main className="app-shell">
      <Joyride
        steps={tourSteps}
        run={runTour}
        continuous
        showProgress
        showSkipButton
        scrollToFirstStep
        callback={handleJoyrideCallback}
        styles={{
          options: {
            zIndex: 10000,
            primaryColor: '#0c8f7f',
            textColor: '#102033',
            borderRadius: 16,
          },
        }}
      />
      <Header onStartTour={() => setRunTour(true)} authUser={authUser} onLogout={handleLogout} />

      <DashboardProductStrip />

      {globalError && <div className="top-error"><AlertTriangle size={18} /> {globalError}</div>}

      <section className="stats-row" data-tour="stats">
        <div><strong>{report?.test_results?.length || 0}</strong><span>Tests parsed</span></div>
        <div><strong>{abnormalCount}</strong><span>Needs attention</span></div>
        <div><strong>{audits?.[audits.length - 1]?.final_safety_status || '—'}</strong><span>Safety status</span></div>
      </section>

      <div className="main-grid">
        <div className="left-column">
          <UploadPanel onPipelineComplete={handlePipelineComplete} />
          <HistoryPanel onSelectReport={loadReport} refreshKey={historyRefreshKey} />
        </div>
        <div className="right-column">
          <SummaryPanel report={report} patientView={patientView} audits={audits} onLanguageChange={changeLanguage} onPrintSummary={handlePrintSummary} />
          <NeedsAttentionPanel report={report} />
          <PatientViewPanel patientView={patientView} />
          <TestResults report={report} />
          <ExtractedTextPanel report={report} />
        </div>
      </div>

      <PrintableSummary report={report} patientView={patientView} audits={audits} />
    </main>
  );
}
createRoot(document.getElementById('root')).render(<App />);