import json
import boto3
import os
from itertools import islice
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb')
templates_table = dynamodb.Table(os.environ['TEMPLATES_TABLE_NAME'])

# Configuration from environment variables
CONFIGURATION_SET = os.environ.get('CONFIGURATION_SET_NAME', '')

# Passed to SendTextMessage as OriginationIdentity. This is the ARN rather than the
# E.164 number on purpose: SendTextMessage only resolves a specific phone-number,
# pool or sender-id resource for IAM authorization when given an ARN. With a bare
# phone number there is no resource in the authorization context, so a resource-scoped
# send policy cannot match and the call is denied.
ORIGINATION_IDENTITY_ARN = os.environ['ORIGINATION_IDENTITY_ARN']

MAX_PRICE = os.environ.get('MAX_PRICE', '2.00')
TTL = int(os.environ.get('MESSAGE_TTL', '120'))


def mask_phone_number(number):
    """Reduce a phone number to a non-identifying form for logging."""
    if not number:
        return '<redacted>'
    digits = ''.join(c for c in number if c.isdigit())
    if len(digits) < 4:
        return '<redacted>'
    return f"***{digits[-4:]}"


def get_template(template_name):
    """Retrieve SMS template from DynamoDB."""
    try:
        response = templates_table.get_item(Key={'TemplateName': template_name})
        if 'Item' not in response:
            raise ValueError(f"Template '{template_name}' not found in DynamoDB")
        return response['Item']['MessageBody']
    except ClientError as e:
        print(f"Error retrieving template: {e}")
        raise


def render_template(template_body, substitutions):
    """Replace {placeholder} variables with substitution values."""
    for key, value in substitutions.items():
        if isinstance(value, list):
            value = value[0]
        template_body = template_body.replace(f"{{{key}}}", str(value))
    return template_body


def send_sms_message(client, destination_number, message_body, message_type):
    """Send SMS via AWS End User Messaging (pinpoint-sms-voice-v2)."""
    try:
        params = {
            'DestinationPhoneNumber': destination_number,
            'MessageBody': message_body,
            'MessageType': message_type,
            'OriginationIdentity': ORIGINATION_IDENTITY_ARN,
            'MaxPrice': MAX_PRICE,
            'TimeToLive': TTL,
        }

        # Only include ConfigurationSetName if configured
        if CONFIGURATION_SET:
            params['ConfigurationSetName'] = CONFIGURATION_SET

        response = client.send_text_message(**params)
        return response['MessageId']

    except ClientError as e:
        print(
            f"Error sending SMS to {mask_phone_number(destination_number)}: "
            f"{e.response['Error']['Message']}"
        )
        raise


def lambda_handler(event, context):
    """Process EventBridge event and send SMS using DynamoDB template."""
    # Extract destination phone number from Addresses
    addresses = event['detail']['Addresses']
    destination_number = None

    for address, config in addresses.items():
        if config.get('ChannelType') == 'SMS':
            destination_number = address
            break

    if not destination_number:
        # Fallback: get second address (legacy behavior)
        destination_number = json.dumps(
            next(islice(event['detail']['Addresses'], 1, None))
        )[1:-1]

    # Recipient numbers are PII. Log a masked form only.
    print(f"Destination: {mask_phone_number(destination_number)}")

    # Get template name from event
    template_name = event['detail']['TemplateConfiguration']['SMSTemplate']['Name']

    # Get substitution variables. These carry customer data (account identifiers,
    # balances), so log only which fields are present, never their values.
    substitutions = addresses[destination_number].get('Substitutions', {})
    print(f"Substitution keys: {sorted(substitutions.keys())}")

    # Retrieve and render template from DynamoDB. The rendered body contains
    # customer data once substituted, so it is not logged.
    template_body = get_template(template_name)
    message_body = render_template(template_body, substitutions)
    print(f"Rendered message from template '{template_name}' ({len(message_body)} chars)")

    # Get message type from event configuration
    message_type = event['detail']['MessageConfiguration']['SMSMessage'].get(
        'MessageType', 'TRANSACTIONAL'
    )

    # Send SMS
    sms_client = boto3.client('pinpoint-sms-voice-v2')
    message_id = send_sms_message(sms_client, destination_number, message_body, message_type)

    print(f"Message sent! Message ID: {message_id}")

    return {
        'statusCode': 200,
        'body': json.dumps({
            'messageId': message_id
        })
    }
