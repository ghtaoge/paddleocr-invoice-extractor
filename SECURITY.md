# Security Policy

## Supported Versions

Security updates apply only to the latest branch. Older versions or forks are not covered.

| Version | Supported |
|---|---|
| latest (`main` branch) | Yes |
| older commits / forks | No |

---

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it through **GitHub Security Advisory**:

1. Go to the repository's [Security tab](https://github.com/Gooeto/paddleocr-invoice-extractor/security)
2. Click "Report a vulnerability"
3. Fill in the advisory form with:
   - Vulnerability type (e.g., XSS, injection, data exposure)
   - Affected component and version
   - Steps to reproduce
   - Potential impact

**Do NOT** report security vulnerabilities through public GitHub Issues, discussions, or social media.

---

## Response Commitment

- **48 hours** — We will acknowledge your report within 48 hours
- **7 days** — We will assess the vulnerability and provide an initial response within 7 days
- Throughout the process, we will keep you informed of progress and remediation plans

If the vulnerability is confirmed:
- We will publish a fix on the `main` branch
- We will credit the reporter in the advisory (unless anonymity is requested)

If the vulnerability is declined:
- We will explain the reasoning and provide guidance on mitigating the risk

---

## Disclaimer

**This project is a teaching case (教学案例) and is NOT intended for production use.**

Specifically:

- This project does NOT implement production-grade security measures (authentication, authorization, rate limiting, input sanitization beyond basic validation)
- OCR recognition results may be inaccurate — do NOT use them for financial, legal, or compliance purposes
- The service processes invoice images locally; no data is sent to third-party servers, but the local runtime environment security is the user's responsibility
- No warranty is provided for data accuracy, security, or reliability

Users deploying this project are responsible for:

- Securing the runtime environment (network isolation, access control)
- Validating OCR results before any real-world application
- Implementing appropriate data protection measures for sensitive invoice information
- Compliance with local regulations regarding invoice data handling

---

## Privacy-Related Security

This project handles sensitive invoice data. Key privacy security measures:

- **Local processing only** — no data transmitted to third-party servers
- **Default desensitization** — sensitive fields are masked in frontend display
- **Privacy scanning** — CI detects sensitive information leaks in the codebase
- **No persistent storage** — invoice data is cleared from memory after recognition

If you discover a privacy leak in the codebase (e.g., real company names, real invoice numbers, private keys, tokens), please report it as a security vulnerability following the process above.
