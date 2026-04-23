export interface Agent {
  id: string;
  name: string;
  tagline: string;
  long_desc: string;
  icon: string;
  trust_score: number;
  data_residency: string[];
  credentials: string[];
  capabilities: string[];
  language_support: string[];
  price_per_task: number;
  sla_p95_seconds: number;
  provider: string;
  offer_id: string;
  input_types: string[];
  input_placeholder: string;
  input_label: string;
}

export const MOCK_AGENTS: Agent[] = [
  {
    id: 'agent-summarizer-001',
    name: 'Legal Document Summarizer',
    tagline: 'Summarizes legal & regulatory documents in Hindi and English',
    long_desc:
      'An AI agent specialized in analyzing legal documents, contracts, and regulatory filings. Produces structured summaries with key provisions, obligations, and risk factors identified. Designed for Indian legal frameworks including DPDP, Companies Act, and SEBI regulations.',
    icon: '📝',
    trust_score: 95,
    data_residency: ['India'],
    credentials: ['ISO 27001', 'DPDP Compliant'],
    capabilities: ['document summary', 'legal analysis', 'risk extraction'],
    language_support: ['English', 'Hindi'],
    price_per_task: 6,
    sla_p95_seconds: 5,
    provider: 'AI Solutions Demo Provider',
    offer_id: 'offer-summarizer-basic',
    input_types: ['application/pdf', 'text/plain'],
    input_placeholder:
      'Paste your legal document text here…\n\nExample: "This Agreement is entered into as of April 1, 2026, between Infosys Ltd ("Service Provider") and ABC Corp ("Client")…"',
    input_label: 'Document text',
  },
  {
    id: 'agent-code-reviewer-001',
    name: 'Code Review Assistant',
    tagline: 'Reviews code for bugs, security issues, and best practices',
    long_desc:
      'An AI agent that performs automated code review. Analyzes code for common vulnerabilities (OWASP Top 10), performance issues, and adherence to coding standards. Supports Python, JavaScript, TypeScript, Go, and Java. Returns structured JSON with severity-ranked findings.',
    icon: '🔍',
    trust_score: 87,
    data_residency: ['India'],
    credentials: ['ISO 27001', 'SEBI Approved'],
    capabilities: ['code review', 'security analysis', 'best practices'],
    language_support: ['English'],
    price_per_task: 10,
    sla_p95_seconds: 30,
    provider: 'AI Solutions Demo Provider',
    offer_id: 'offer-code-review-basic',
    input_types: ['text/plain', 'application/zip'],
    input_placeholder:
      'Paste your code here…\n\nExample:\ndef divide(a, b):\n    return a / b\n\n# Add language in the field below',
    input_label: 'Code snippet',
  },
  {
    id: 'agent-data-extractor-001',
    name: 'Invoice Data Extractor',
    tagline: 'Extracts structured data from invoices and financial documents',
    long_desc:
      'An AI agent that processes scanned invoices, receipts, and financial documents to extract structured data: line items, amounts, dates, vendor information, and tax details. Returns standardized JSON output compatible with Tally, SAP, and Zoho Books.',
    icon: '📊',
    trust_score: 92,
    data_residency: ['India'],
    credentials: ['DPDP Compliant', 'RBI Framework'],
    capabilities: ['data extraction', 'ocr', 'invoice processing'],
    language_support: ['English', 'Hindi', 'Tamil'],
    price_per_task: 4,
    sla_p95_seconds: 10,
    provider: 'AI Solutions Demo Provider',
    offer_id: 'offer-data-extractor-basic',
    input_types: ['image/jpeg', 'image/png', 'application/pdf'],
    input_placeholder:
      'Paste invoice text or describe the document…\n\nExample: "Invoice #INV-2026-0441 from Infosys Ltd, dated 15 Apr 2026. Services: Cloud hosting ₹45,000, Support ₹8,000. GST 18%."',
    input_label: 'Invoice text or description',
  },
];

export const MOCK_RESULTS: Record<string, object> = {
  'agent-summarizer-001': {
    summary:
      'The agreement establishes a cloud services contract between Infosys Ltd and ABC Corp for a term of 24 months. Service Provider retains full IP ownership. Client granted non-exclusive usage rights.',
    keyProvisions: [
      'Clause 3.2: Liability capped at 3 months of contract value (₹1,50,000)',
      'Clause 7.1: Unilateral arbitration clause — disputes resolved by SP-nominated arbitrator',
      'Clause 12: Auto-renewal unless 90-day notice given by Client',
      'Clause 15.3: Data stored on Indian servers only (DPDP compliant)',
    ],
    riskFactors: [
      'HIGH: Unilateral arbitration clause (Clause 7.1)',
      'MEDIUM: Auto-renewal with long notice period (Clause 12)',
      'LOW: Broad IP assignment language in Clause 9',
    ],
    language: 'en',
    wordCount: 3241,
    confidence: 0.94,
  },
  'agent-code-reviewer-001': {
    review:
      'Code analysis complete. Found 2 critical vulnerabilities and 4 medium-severity issues. Overall security score: 72/100.',
    issues: [
      {
        severity: 'CRITICAL',
        line: 3,
        rule: 'ZeroDivisionError',
        description: 'Division by zero: no guard for b == 0',
        suggestion: 'Add: if b == 0: raise ValueError("Divisor cannot be zero")',
      },
      {
        severity: 'CRITICAL',
        line: 3,
        rule: 'TypeSafety',
        description: 'No type annotations — inputs unvalidated',
        suggestion: 'def divide(a: float, b: float) -> float:',
      },
      {
        severity: 'MEDIUM',
        line: 1,
        rule: 'MissingDocstring',
        description: 'No docstring for public function',
        suggestion: 'Add docstring describing parameters and return type',
      },
      {
        severity: 'LOW',
        line: 3,
        rule: 'NamingConvention',
        description: 'Single-letter parameter names reduce readability',
        suggestion: 'Rename a → dividend, b → divisor',
      },
    ],
    score: 72,
    recommendations: [
      'Add input validation before all arithmetic operations',
      'Use type hints throughout the codebase',
      'Consider adding unit tests for edge cases (b=0, very large numbers)',
    ],
    language: 'python',
  },
  'agent-data-extractor-001': {
    vendor: 'Infosys Limited',
    vendorGSTIN: '29AABCI1682H1ZK',
    invoiceNumber: 'INV-2026-04187',
    invoiceDate: '2026-04-15',
    dueDate: '2026-05-15',
    lineItems: [
      { description: 'Cloud Hosting Services', hsn: '998314', qty: 1, unitPrice: 45000, amount: 45000 },
      { description: 'Technical Support (20 hrs)', hsn: '998313', qty: 20, unitPrice: 400, amount: 8000 },
    ],
    subtotal: 53000,
    gstRate: '18%',
    gstAmount: 9540,
    totalAmount: 62540,
    currency: 'INR',
    paymentTerms: 'Net 30',
    confidence: 0.97,
  },
};
