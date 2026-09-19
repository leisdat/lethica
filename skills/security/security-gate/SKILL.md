# Security Gate

## PASS

Allowed when:

- no known critical vulnerability
- no exposed secret
- authentication/authorization validated
- sensitive data protected
- relevant security tests passed

## FAIL

Block release when:

- critical vulnerability exists
- active secret exposed
- authentication bypass exists
- privilege escalation exists
- sensitive data can be accessed improperly

## Output

Security Status:
PASS / FAIL / BLOCKED

Findings:
- severity
- location
- impact
- remediation
