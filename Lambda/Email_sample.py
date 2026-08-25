import json
import boto3
import html
import os
from itertools import islice
from botocore.exceptions import ClientError

sesv2 = boto3.client('sesv2')

# Configuration from environment variables
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# The only From address this function is permitted to send as. The Lambda's IAM
# policy enforces the same constraint via the ses:FromAddress condition key;
# checking here too produces a clear error instead of an AccessDenied at send time.
SES_FROM_ADDRESS = os.environ.get('SES_FROM_ADDRESS', '')


def mask_email(address):
    """Reduce an email address to a non-identifying form for logging."""
    if not address or '@' not in address:
        return '<redacted>'
    local, _, domain = address.partition('@')
    return f"{local[:1]}***@{domain}"


def first_value(substitutions, key, default):
    """Read a substitution value, which may be a bare value or a single-item list."""
    value = substitutions.get(key, default)
    if isinstance(value, list):
        value = value[0] if value else default
    return value


def build_html_body(substitutions):
    """Build HTML email body from substitution variables.

    Every interpolated value originates from the request payload, so each one is
    HTML-escaped before it reaches the template. Without this, a caller could
    inject arbitrary markup, links or forms into a message delivered from a
    verified sending domain. For anything beyond a sample, prefer SES templates
    with substitution variables over assembling HTML in application code.
    """
    product_name = html.escape(str(first_value(substitutions, 'productName', 'Account')))
    membership_number = html.escape(str(first_value(substitutions, 'membershipNumber', '****0000')))
    threshold = html.escape(str(first_value(substitutions, 'threshold', '0.00')))

    return f"""
    <html>
    <body>
        <h2>Available Credit Alert</h2>
        <p>Dear customer,</p>
        <p>This is a notification that your {product_name} account,
        ending in {membership_number}, has reached the ${threshold}
        balance threshold.</p>
        <p>Please log in to your account for more details.</p>
        <p><a href="https://example.com/account">View Account</a></p>
    </body>
    </html>
    """


def lambda_handler(event, context):
    """Process EventBridge event and send email via Amazon SES v2."""
    # Extract email destination from Addresses
    addresses = event['detail']['Addresses']
    email_destination = None

    for address, config in addresses.items():
        if config.get('ChannelType') == 'EMAIL':
            email_destination = address
            break

    if not email_destination:
        # Fallback: get first address (legacy behavior)
        email_destination = json.dumps(
            next(islice(event['detail']['Addresses'], 0, None))
        )[1:-1]

    # Recipient addresses are PII. Log a masked form only.
    print(f"Email destination: {mask_email(email_destination)}")

    # Get email configuration
    email_config = event['detail']['MessageConfiguration']['EmailMessage']
    from_address = email_config['FromAddress']
    reply_to = email_config.get('ReplyToAddresses', [from_address])
    substitutions = email_config.get('Substitutions', {})

    # Reject a From address the deployment is not configured to send as.
    if SES_FROM_ADDRESS and from_address != SES_FROM_ADDRESS:
        raise ValueError(
            "FromAddress in the event is not the configured sending identity"
        )

    # Build email content
    html_body = build_html_body(substitutions)
    subject = first_value(substitutions, 'subject', 'Account Notification')

    try:
        response = sesv2.send_email(
            FromEmailAddress=from_address,
            ReplyToAddresses=reply_to if isinstance(reply_to, list) else [reply_to],
            Destination={
                'ToAddresses': [email_destination]
            },
            Content={
                'Simple': {
                    'Subject': {
                        'Data': subject,
                        'Charset': 'UTF-8'
                    },
                    'Body': {
                        'Html': {
                            'Data': html_body,
                            'Charset': 'UTF-8'
                        }
                    }
                }
            }
        )

        print(f"Email sent! Message ID: {response['MessageId']}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'messageId': response['MessageId']
            })
        }

    except ClientError as e:
        print(f"Error sending email: {e.response['Error']['Message']}")
        raise
