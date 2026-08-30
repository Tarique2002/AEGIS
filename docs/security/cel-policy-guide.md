# AEGIS CEL Policy Guide

## 1. Introduction
Google Common Expression Language (CEL) provides fast, non-Turing-complete, safely sandboxed expression evaluation for authorization policies in AEGIS.

---

## 2. Controlled Variables Available in CEL
| Variable | Description | Example Attributes |
| :--- | :--- | :--- |
| `subject` | Authenticated actor identity | `subject.user_id`, `subject.tenant_id`, `subject.roles`, `subject.permissions`, `subject.scopes` |
| `resource` | Target resource attributes | `resource.owner_id`, `resource.tenant_id`, `resource.sensitivity`, `resource.risk_level` |
| `action` | Action/permission name | `action == "task:read"` |
| `environment` | Contextual runtime data | `environment.timestamp`, `environment.environment` |
| `request` | Request parameters | `request.parameters` |
| `token` | Verified JWT claims | `token.scopes`, `token.sub` |

---

## 3. Example CEL Expressions
1. **Tenant Ownership Match**:
   ```cel
   subject.tenant_id == resource.tenant_id
   ```

2. **Role & Action Constraint**:
   ```cel
   "admin" in subject.roles && action == "task:delete"
   ```

3. **Sensitivity & Permission Guard**:
   ```cel
   resource.sensitivity != "critical" || "security:admin" in subject.permissions
   ```

4. **Risk Level Gate**:
   ```cel
   resource.risk_level == "LOW" || "operator:execute" in subject.permissions
   ```
