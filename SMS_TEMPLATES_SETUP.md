# SMS Templates Setup Guide

> **Disclaimer**
>
> This is sample code, for non-production usage. You should work with your security and legal teams to meet your organizational security, regulatory and compliance requirements before deployment.

## Overview

This solution uses DynamoDB to store SMS templates, enabling message content updates without Lambda redeployment. This is particularly useful in regulated industries where notification wording changes frequently.

## Template Format

Templates use `{variableName}` syntax for substitutions:

```
Alert: Your {productName} account ending in {membershipNumber} has reached the ${threshold} balance threshold.
```

Variables are replaced at runtime from the `Substitutions` object in your event payload.

## Adding Templates

### Using AWS CLI

```bash
# Balance alert template
aws dynamodb put-item \
  --table-name YOUR_STACK_NAME-SMSTemplates \
  --item '{
    "TemplateName": {"S": "balance-alert"},
    "MessageBody": {"S": "Alert: Your {productName} account ending in {membershipNumber} has reached the ${threshold} balance threshold."},
    "Version": {"S": "1"},
    "LastUpdated": {"S": "2026-01-15T13:00:00Z"}
  }'

# Payment reminder template
aws dynamodb put-item \
  --table-name YOUR_STACK_NAME-SMSTemplates \
  --item '{
    "TemplateName": {"S": "payment-reminder"},
    "MessageBody": {"S": "Payment Reminder: Your {productName} payment of ${amount} is due on {dueDate}."},
    "Version": {"S": "1"},
    "LastUpdated": {"S": "2026-01-15T13:00:00Z"}
  }'

# Account update template
aws dynamodb put-item \
  --table-name YOUR_STACK_NAME-SMSTemplates \
  --item '{
    "TemplateName": {"S": "account-update"},
    "MessageBody": {"S": "Account Update: Your {productName} account {membershipNumber} has been updated. Log in for details."},
    "Version": {"S": "1"},
    "LastUpdated": {"S": "2026-01-15T13:00:00Z"}
  }'
```

### Using Python Script

```python
import boto3
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('YOUR_STACK_NAME-SMSTemplates')

templates = [
    {
        'TemplateName': 'balance-alert',
        'MessageBody': 'Alert: Your {productName} account ending in {membershipNumber} has reached the ${threshold} balance threshold.',
        'Version': '1',
        'LastUpdated': datetime.utcnow().isoformat()
    },
    {
        'TemplateName': 'payment-reminder',
        'MessageBody': 'Payment Reminder: Your {productName} payment of ${amount} is due on {dueDate}.',
        'Version': '1',
        'LastUpdated': datetime.utcnow().isoformat()
    },
    {
        'TemplateName': 'account-update',
        'MessageBody': 'Account Update: Your {productName} account {membershipNumber} has been updated. Log in for details.',
        'Version': '1',
        'LastUpdated': datetime.utcnow().isoformat()
    }
]

for template in templates:
    table.put_item(Item=template)
    print(f"Added template: {template['TemplateName']}")
```

## Updating Templates (No Redeployment)

```bash
aws dynamodb update-item \
  --table-name YOUR_STACK_NAME-SMSTemplates \
  --key '{"TemplateName": {"S": "balance-alert"}}' \
  --update-expression "SET MessageBody = :msg, Version = :ver, LastUpdated = :dt" \
  --expression-attribute-values '{
    ":msg": {"S": "URGENT: Your {productName} ending in {membershipNumber} balance is ${threshold}. Act now."},
    ":ver": {"S": "2"},
    ":dt": {"S": "2026-07-08T00:00:00Z"}
  }'
```

## Migrating from Amazon Pinpoint Templates

1. List your existing Pinpoint templates:
   ```bash
   aws pinpoint-sms-voice-v2 describe-registration-attachments
   ```

2. For each template, create a DynamoDB item preserving the template name:
   - Use the same `TemplateName` as your Pinpoint template
   - Copy the message body
   - Convert placeholder syntax: `{{.variable}}` → `{variable}`

3. No changes needed to your event payloads — the `TemplateConfiguration.SMSTemplate.Name` field maps directly.

## DynamoDB Costs

| Usage | Monthly Cost |
|-------|-------------|
| 1M template reads (on-demand) | ~$0.25 |
| Storage (< 1 KB per template) | Negligible |
| Total for 1M messages/month | ~$0.25 |

## Best Practices

- **Version your templates**: Increment the `Version` field on each update for audit trail
- **Use descriptive names**: `balance-alert`, `payment-reminder`, `otp-verification`
- **Test before updating**: Use a test event to validate template rendering before updating production
- **Monitor**: Set up CloudWatch alarms on DynamoDB read errors
