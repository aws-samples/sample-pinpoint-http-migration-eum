#!/usr/bin/env python3
"""Generate a test payload for the notification API from environment variables.

Kept separate from events/sample-payload.json so that no real phone number or email
address is ever committed to this repository. Prints the payload to stdout.

Required environment variables:
  TEST_SMS_DESTINATION    Destination phone number in E.164 format, e.g. +15551234567
  TEST_EMAIL_DESTINATION  Destination email address
  SES_FROM_ADDRESS        Sending identity; must match the SESFromAddress the stack
                          was deployed with, or the Email function rejects the event

Optional:
  SMS_TEMPLATE_NAME       DynamoDB template to render (default: balance-alert)
  TEST_PRODUCT_NAME       Substitution value (default: CHEQUING)
  TEST_MEMBERSHIP_NUMBER  Substitution value (default: ****5493)
  TEST_THRESHOLD          Substitution value (default: 100.00)

Usage:
  export TEST_SMS_DESTINATION="+15551234567"
  export TEST_EMAIL_DESTINATION="you@yourdomain.com"
  export SES_FROM_ADDRESS="alerts@yourdomain.com"
  python3 events/generate-payload.py > payload.json
"""
import json
import os
import sys

REQUIRED = ('TEST_SMS_DESTINATION', 'TEST_EMAIL_DESTINATION', 'SES_FROM_ADDRESS')


def build_payload(sms_destination, email_destination, from_address,
                  template_name='balance-alert', product_name='CHEQUING',
                  membership_number='****5493', threshold='100.00',
                  trace_id='local-test-001'):
    """Build the API request body. Detail is a JSON string, as the VTL mapping expects."""
    substitutions = {
        'productName': [product_name],
        'membershipNumber': [membership_number],
        'threshold': [threshold],
    }

    detail = {
        'TraceId': trace_id,
        'TemplateConfiguration': {'SMSTemplate': {'Name': template_name}},
        'MessageConfiguration': {
            'EmailMessage': {
                'Substitutions': substitutions,
                'FromAddress': from_address,
                'ReplyToAddresses': [from_address],
            },
            'SMSMessage': {'MessageType': 'TRANSACTIONAL'},
        },
        'Addresses': {
            email_destination: {'ChannelType': 'EMAIL'},
            sms_destination: {'ChannelType': 'SMS', 'Substitutions': substitutions},
        },
    }

    return {'items': [{
        'Detail': json.dumps(detail),
        'DetailType': 'Customer Notification',
        'Source': 'com.example.notifications',
    }]}


def main():
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        sys.stderr.write(
            'Missing required environment variable(s): ' + ', '.join(missing) + '\n\n'
            'Example:\n'
            '  export TEST_SMS_DESTINATION="+15551234567"\n'
            '  export TEST_EMAIL_DESTINATION="you@yourdomain.com"\n'
            '  export SES_FROM_ADDRESS="alerts@yourdomain.com"\n'
        )
        return 1

    payload = build_payload(
        sms_destination=os.environ['TEST_SMS_DESTINATION'],
        email_destination=os.environ['TEST_EMAIL_DESTINATION'],
        from_address=os.environ['SES_FROM_ADDRESS'],
        template_name=os.environ.get('SMS_TEMPLATE_NAME', 'balance-alert'),
        product_name=os.environ.get('TEST_PRODUCT_NAME', 'CHEQUING'),
        membership_number=os.environ.get('TEST_MEMBERSHIP_NUMBER', '****5493'),
        threshold=os.environ.get('TEST_THRESHOLD', '100.00'),
    )
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
