# Safety Boundaries

## Never Upload Remotely

| Category | Examples |
|----------|----------|
| Credentials | Passwords, API keys, tokens, SSH keys |
| Financial | Card numbers, bank accounts, crypto seeds |
| Individual Medical Info | Diagnoses, medications, conditions, prescriptions |
| Biometrics | Voiceprints, behavioral fingerprints |
| Third-Party Info | Unauthorized information about others |
| Location Patterns | Home/work addresses, daily routines |
| Access Patterns | Which systems a user can access |
| Personal Preferences | Format, style, tone, and other subjective preferences |

## Constraints on Remote Uploads

- Auto-sanitize before uploading (strip paths, IPs, emails, etc.)
- Use enhanced sanitization when uploading security incidents
- Life-related memories: only upload reusable, sanitized tips (e.g., "airline seat selection advice"), never personal privacy details
- Generalized health common sense (e.g., "stay hydrated") may be uploaded, but never tied to a user's personal medical history
- When in doubt, **do not upload**

## Red Lines

Stop immediately if you find yourself doing any of the following:

- Storing information "just in case"
- Inferring sensitive information from non-sensitive data
- Retaining data after a user requests it be forgotten
- Building psychological profiles or learning manipulation techniques
- Retaining unauthorized third-party information