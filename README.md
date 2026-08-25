# Migrating from Amazon Pinpoint to AWS End User Messaging with Event-Driven Architecture

> **Disclaimer**
>
> This is sample code, for non-production usage. You should work with your security and legal teams to meet your organizational security, regulatory and compliance requirements before deployment.

This sample demonstrates a serverless, event-driven architecture for migrating customer notification workloads from Amazon Pinpoint (reaching End of Life October 30, 2026) to AWS End User Messaging (EUM) and Amazon SES. It uses API Gateway, Amazon EventBridge, AWS Lambda, and DynamoDB to provide a scalable, template-driven messaging solution that routes SMS and email notifications through a single API endpoint.

> **Use Case**: Organizations using Amazon Pinpoint's HTTP endpoint for transactional notifications (balance alerts, payment reminders, account updates) that need to migrate before EOL while maintaining compliance with messaging regulations (Short Codes, 10DLC, sender IDs).

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│                 │    │                 │    │                 │
│   HTTP Client   │───▶│   API Gateway   │───▶│   EventBridge   │
│  (Mulesoft,     │    │   (REST API)    │    │   (Custom Bus)  │
│   App, etc.)    │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                              ┌─────────┴─────────┐
                                              │  EventBridge Rules │
                                              │  (Content-based    │
                                              │   routing)         │
                                              └─────────┬─────────┘
                                                   │         │
                                    ┌──────────────┘         └──────────────┐
                                    ▼                                        ▼
                          ┌─────────────────┐                      ┌─────────────────┐
                          │  Email Lambda   │                      │   SMS Lambda    │
                          │                 │                      │                 │
                          └────────┬────────┘                      └────────┬────────┘
                                   │                                        │
                                   │                               ┌────────▼────────┐
                                   │                               │    DynamoDB     │
                                   │                               │  SMS Templates  │
                                   │                               └────────┬────────┘
                                   │                                        │
                                   ▼                                        ▼
                          ┌─────────────────┐                      ┌─────────────────┐
                          │   Amazon SES    │                      │   AWS End User  │
                          │                 │                      │   Messaging     │
                          └─────────────────┘                      └─────────────────┘
```

## How It Works

1. **API Gateway** receives HTTP POST requests (compatible with existing Pinpoint HTTP endpoint payload structure) and publishes events directly to EventBridge using VTL mapping — no Lambda needed for ingestion.

2. **EventBridge** routes events based on content:
   - Events with `MessageConfiguration.EmailMessage.FromAddress` → Email Lambda
   - Events with `MessageConfiguration.SMSMessage.MessageType` → SMS Lambda

3. **SMS Lambda** retrieves message templates from DynamoDB, renders them with substitution variables, and sends via AWS End User Messaging (pinpoint-sms-voice-v2 API).

4. **Email Lambda** constructs HTML emails with substitution variables and sends via Amazon SES v2.

5. **DynamoDB Templates** enable updating message content without code deployments — critical for regulated industries where message wording changes frequently.

## Why This Architecture?

| Challenge | Solution |
|-----------|----------|
| Pinpoint EOL (Oct 2026) | Direct migration to EUM + SES with familiar payload structure |
| Multiple notification channels (SMS + Email) | Single API endpoint with content-based routing |
| Regulatory compliance (Short Codes, 10DLC) | EUM supports dedicated origination identities |
| Frequent template changes | DynamoDB-backed templates — no redeployment needed |
| Integration with existing middleware (Mulesoft, etc.) | REST API maintains HTTP POST interface |
| Cost transparency | Pay-per-use with clear per-service breakdown |

## Prerequisites

- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) installed and configured
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html) installed
- [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) installed
- An AWS account with permissions to create API Gateway, EventBridge, Lambda, DynamoDB, SES, and IAM resources
- A registered origination identity (Short Code, 10DLC, or Long Code) in AWS End User Messaging
- A verified sending identity in Amazon SES

## Deployment

### 1. Clone and deploy

```bash
git clone https://github.com/aws-samples/pinpoint-to-eum-eventdriven-messaging
cd pinpoint-to-eum-eventdriven-messaging

sam deploy --guided
```

First, look up the ARN of your origination identity:

```bash
aws pinpoint-sms-voice-v2 describe-phone-numbers \
  --query "PhoneNumbers[].{Number:PhoneNumber,Arn:PhoneNumberArn}" --output table
```

During the prompts:
- Enter a stack name
- Enter your AWS Region
- Provide your origination identity ARN (`OriginationIdentityArn`) from the command above. The ARN is required rather than the plain `+1...` number: `SendTextMessage` only resolves a specific resource for IAM authorization when given an ARN, which is what allows the send permission to be scoped to that one identity instead of `*`. Pool and sender ID ARNs work too.
- Provide your verified SES email address
- Leave `ConfigurationSetName` empty unless you have created an End User Messaging SMS configuration set. It is not an email address and not an SES setting.
- Optionally adjust `LogRetentionInDays` (default 14)
- Allow SAM CLI to create IAM roles

### 2. Add SMS templates to DynamoDB

```bash
aws dynamodb put-item \
  --table-name YOUR_STACK_NAME-SMSTemplates \
  --item '{
    "TemplateName": {"S": "balance-alert"},
    "MessageBody": {"S": "Alert: Your {productName} account ending in {membershipNumber} has reached the ${threshold} balance threshold."},
    "Version": {"S": "1"},
    "LastUpdated": {"S": "2026-01-15T13:00:00Z"}
  }'
```

See [SMS_TEMPLATES_SETUP.md](SMS_TEMPLATES_SETUP.md) for complete template management guide.

### 3. Test the endpoint

The endpoint uses IAM authorization, so requests must be signed with SigV4. An
unsigned `curl` returns `403 Missing Authentication Token`.

**Option A — invoke the functions locally, no deployment needed.** Uses the checked-in
sample payload, which contains placeholder destinations only:

```bash
sam local invoke SMSLambdaFunction --event events/sample-payload.json
sam local invoke EmailLambdaFunction --event events/sample-payload.json
```

**Option B — end-to-end against the deployed endpoint, using [awscurl](https://github.com/okigan/awscurl).**
Set your own destinations as environment variables; `events/generate-payload.py` builds the
request body so that no real phone number or email address ends up in a file:

```bash
pip install awscurl

export TEST_SMS_DESTINATION="+15551234567"        # your phone, E.164
export TEST_EMAIL_DESTINATION="you@yourdomain.com"
export SES_FROM_ADDRESS="alerts@yourdomain.com"   # must match the deployed SESFromAddress

awscurl --service execute-api --region REGION \
  -X POST "https://YOUR-API-ID.execute-api.REGION.amazonaws.com/prod/" \
  -H 'Content-Type: application/json' \
  -d "$(python3 events/generate-payload.py)"
```

**Option C — end-to-end with `curl` using SigV4 signing:**

```bash
curl -X POST "https://YOUR-API-ID.execute-api.REGION.amazonaws.com/prod/" \
  --aws-sigv4 "aws:amz:REGION:execute-api" \
  --user "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" \
  -H "x-amz-security-token: $AWS_SESSION_TOKEN" \
  -H 'Content-Type: application/json' \
  -d "$(python3 events/generate-payload.py)"
```

`generate-payload.py` also accepts `SMS_TEMPLATE_NAME`, `TEST_PRODUCT_NAME`,
`TEST_MEMBERSHIP_NUMBER` and `TEST_THRESHOLD` to exercise other templates and
substitution values. It exits with an error rather than falling back to a default
destination, so a misconfigured shell cannot send to an unintended recipient.

The calling IAM principal needs `execute-api:Invoke` on the method. For example:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "execute-api:Invoke",
      "Resource": "arn:aws:execute-api:REGION:ACCOUNT_ID:YOUR-API-ID/prod/POST/"
    }
  ]
}
```

## Migrating from Amazon Pinpoint

### Template Migration

Your existing Pinpoint templates can be migrated to DynamoDB preserving the same template names:

1. Export your Pinpoint message templates
2. Create DynamoDB items with the same `TemplateName`
3. Copy message body content (update placeholder syntax from `{{.variable}}` to `{variable}`)
4. Deploy — no changes needed to your event payload structure

### API Compatibility

The API Gateway endpoint accepts the same payload structure used by Pinpoint's campaign/journey triggers, making it a drop-in replacement for applications using the HTTP endpoint.

### Origination Identity Migration

| Pinpoint Feature | EUM Equivalent |
|------------------|----------------|
| Short Code | Short Code (same registration) |
| 10DLC | 10DLC (same registration) |
| Long Code | Long Code |
| Sender ID | Sender ID |

Your existing registrations carry over — no re-registration needed.

## Cost Estimate (1M messages/month)

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| API Gateway (REST) | 1M requests | $3.50 |
| EventBridge | 1M events | $1.00 |
| Lambda (Email) | 1M invocations, 2s avg | ~$2.50 |
| Lambda (SMS) | 1M invocations, 1s avg | ~$1.75 |
| DynamoDB | 1M reads (on-demand) | ~$0.25 |
| Amazon SES | 1M emails | $100.00 |
| SMS (varies by country) | 1M messages | Varies |
| **Total (excl. SMS)** | | **~$109** |

> **Note**: SMS per-message costs vary by country and number type. See [AWS End User Messaging pricing](https://aws.amazon.com/end-user-messaging/pricing/).

## Project Structure

```
├── README.md                  # This file
├── template.yaml              # SAM template (full stack)
├── Lambda/
│   ├── SMS_sample_ddb.py      # SMS processor with DynamoDB template lookup
│   └── Email_sample.py        # Email processor with SES v2
├── events/
│   ├── sample-payload.json    # Static test payload (placeholder destinations)
│   └── generate-payload.py    # Builds a payload from environment variables
├── SMS_TEMPLATES_SETUP.md     # DynamoDB template management guide
└── LICENSE                    # MIT-0
```

## Security Considerations

### What this sample does

- **The endpoint requires authentication.** The POST method is deployed with `AuthorizationType: AWS_IAM`, so callers must present valid SigV4-signed requests and hold `execute-api:Invoke` on the method. Without this, the endpoint would be an open relay: anyone with the URL could send SMS and email to arbitrary destinations from your sender identity and at your cost.
- **Email sending is scoped to one address.** The Email function's IAM policy allows only `ses:SendEmail`, only on the identity for the `SESFromAddress` you supply, and only with a `ses:FromAddress` condition matching that address. The function also rejects any event whose `FromAddress` differs.
- **SMS sending is scoped to one origination identity.** The SMS function's IAM policy allows only `sms-voice:SendTextMessage`, and only on the ARN you supply in `OriginationIdentityArn`. This depends on the function passing that ARN as `OriginationIdentity`: [`SendTextMessage` supports resource-level permissions](https://docs.aws.amazon.com/service-authorization/latest/reference/list_pinpoint-sms-voice-v2.html) on `phone-number`, `pool` and `sender-id` resources, but the `phone-number` ARN is keyed on the phone number *ID*, so passing a bare E.164 number leaves no resource in the authorization context and any scoped policy is denied.
- **Template access is read-only.** The SMS function can read the DynamoDB templates table and nothing else.
- **Payload values are HTML-escaped** before being interpolated into the email body, so a caller cannot inject markup or links into a message sent from your verified domain.
- **Logs exclude recipient PII.** Phone numbers and email addresses are masked, message bodies are not logged, and both log groups have an explicit retention period (`LogRetentionInDays`, default 14 days).
- **No hardcoded credentials** — all configuration is via SAM parameters and environment variables.

### What this sample does not do

These are deliberate omissions to keep the sample readable. Consider them before
using this pattern for anything real:

- No WAF, usage plan, request throttling or reserved concurrency, so there is no ceiling on volume or spend from an authenticated caller
- No dead-letter queues or retry policy, so failed events are dropped
- No payload schema validation between API Gateway and EventBridge
- No X-Ray tracing or end-to-end request correlation
- No write-access controls or change auditing on the templates table beyond default IAM
- No VPC endpoints (available, but not configured here)

### Changing the authorizer

`AWS_IAM` is the shipped default because it needs no extra infrastructure. If your
callers cannot sign requests, replace it rather than removing it:

| Authorizer | When it fits | Template change |
|---|---|---|
| IAM / SigV4 (default) | Callers are AWS principals or middleware that can sign | `AuthorizationType: AWS_IAM` |
| Cognito user pool | Callers authenticate as end users | `AuthorizationType: COGNITO_USER_POOLS` plus `AuthorizerId` |
| Lambda authorizer | Callers present an existing token your code validates | `AuthorizationType: CUSTOM` plus `AuthorizerId` |
| API key + usage plan | Machine callers, and you want per-key rate limits | `ApiKeyRequired: true` plus `AWS::ApiGateway::UsagePlan` and `UsagePlanKey` |

An API key alone is an identifier, not a credential. If you use one, pair it with a
usage plan so a leaked key has a bounded blast radius.

## Extending the Solution

- **Add channels**: WhatsApp via Social Messaging, Push via SNS — add new EventBridge rules and Lambda functions
- **Add validation**: Insert a validation Lambda between API Gateway and EventBridge
- **Add retry/DLQ**: Configure EventBridge dead-letter queues and Lambda retry policies
- **Add observability**: CloudWatch dashboards, X-Ray tracing, EventBridge archive for replay
- **Add batching**: SQS between EventBridge and Lambda for high-throughput scenarios

## Clean Up

```bash
sam delete --stack-name YOUR_STACK_NAME
```

## Related Resources

- [AWS End User Messaging Documentation](https://docs.aws.amazon.com/end-user-messaging/)
- [Amazon Pinpoint Migration Guide](https://docs.aws.amazon.com/pinpoint/latest/developerguide/)
- [EventBridge Patterns on Serverless Land](https://serverlessland.com/patterns?services=eventbridge)
- [SMS Delivery Best Practices](https://aws.amazon.com/blogs/messaging-and-targeting/a-guide-to-optimizing-sms-delivery-and-best-practices/)
- [SAM Developer Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/)

---

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
