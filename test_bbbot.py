import unittest
from unittest.mock import patch, MagicMock
import os
import json
from datetime import datetime

# Add the parent directory to sys.path to allow importing bbbot
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import bbbot # Import the script to be tested

class TestBBBotUtils(unittest.TestCase):

    def test_normalize(self):
        self.assertEqual(bbbot.normalize("  Test String  "), "test string")
        self.assertEqual(bbbot.normalize("AlreadyNormalized"), "alreadynormalized")
        self.assertEqual(bbbot.normalize("UPPERCASE"), "uppercase")
        self.assertEqual(bbbot.normalize(""), "")

class TestBBBotFindProductUrls(unittest.TestCase):

    @patch('bbbot.requests.post')
    @patch('bbbot.PERPLEXITY_API_KEY', 'fake_api_key') # Ensure API key is set for tests
    def test_find_product_urls_api_success(self, mock_post):
        # Simulate a successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": '''{
                        "productos": [
                            {"nombre": "Product A", "url": "http://example.com/a"},
                            {"nombre": "Product B", "url": "http://example.com/b"}
                        ]
                    }'''
                }
            }]
        }
        mock_post.return_value = mock_response

        # Mock datetime to make it always Monday
        with patch('bbbot.datetime') as mock_datetime:
            mock_datetime.now.return_value.weekday.return_value = 0 # Monday

            # Mock open for saving the response
            with patch('builtins.open', unittest.mock.mock_open()) as mock_file:
                urls = bbbot.find_product_urls()
                mock_file.assert_called_once_with(bbbot.PERPLEXITY_SAVE_FILE, 'w')

        self.assertEqual(len(urls), 2)
        self.assertIn("http://example.com/a", urls)
        self.assertIn("http://example.com/b", urls)
        mock_post.assert_called_once()

    @patch('bbbot.requests.post')
    @patch('bbbot.PERPLEXITY_API_KEY', 'fake_api_key')
    def test_find_product_urls_api_error(self, mock_post):
        # Simulate an API error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = bbbot.requests.exceptions.HTTPError("API Error")
        mock_post.return_value = mock_response

        with patch('bbbot.datetime') as mock_datetime:
            mock_datetime.now.return_value.weekday.return_value = 0 # Monday
            urls = bbbot.find_product_urls()

        self.assertEqual(urls, [])
        mock_post.assert_called_once()

    @patch('bbbot.PERPLEXITY_API_KEY', 'fake_api_key')
    def test_find_product_urls_load_from_file_success(self):
        # Simulate existing PERPLEXITY_SAVE_FILE
        mock_products_data = [
            {"nombre": "Product C", "url": "http://example.com/c"},
            {"nombre": "Product D", "url": "http://example.com/d"}
        ]
        mock_open_content = json.dumps(mock_products_data)

        with patch('bbbot.datetime') as mock_datetime:
            mock_datetime.now.return_value.weekday.return_value = 1 # Not Monday

            with patch('builtins.open', unittest.mock.mock_open(read_data=mock_open_content)) as mock_file:
                with patch('os.path.exists') as mock_exists: # Ensure this is not needed if open handles it
                    mock_exists.return_value = True # Though mock_open should handle this
                    urls = bbbot.find_product_urls()
                    mock_file.assert_called_with(bbbot.PERPLEXITY_SAVE_FILE, 'r')

        self.assertEqual(len(urls), 2)
        self.assertIn("http://example.com/c", urls)

    @patch('bbbot.PERPLEXITY_API_KEY', 'fake_api_key')
    def test_find_product_urls_load_from_file_not_found(self):
        with patch('bbbot.datetime') as mock_datetime:
            mock_datetime.now.return_value.weekday.return_value = 1 # Not Monday
            with patch('builtins.open', side_effect=FileNotFoundError) as mock_file:
                urls = bbbot.find_product_urls()

        self.assertEqual(urls, [])

class TestBBBotGenerateNewsletter(unittest.TestCase):

    @patch('bbbot.client.chat.completions.create')
    @patch('bbbot.OPENAI_KEY', 'fake_openai_key') # Ensure API key is set
    def test_generate_newsletter_success(self, mock_create_completion):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Generated HTML Newsletter"
        mock_create_completion.return_value = mock_response

        product_data = {
            "nombre": "Test Product", "marca": "Test Brand", "precio": "10",
            "tecnologia": "Test Tech", "descripcion": "Test Desc",
            "ingredientes": ["i1", "i2"], "beneficios": ["b1", "b2"],
            "tipo_piel": "All", "estudios_clinicos": "None", "sostenibilidad": "Good"
        }
        content = bbbot.generate_newsletter(product_data)

        self.assertEqual(content, "Generated HTML Newsletter")
        mock_create_completion.assert_called_once()

    @patch('bbbot.client.chat.completions.create')
    @patch('bbbot.OPENAI_KEY', 'fake_openai_key')
    def test_generate_newsletter_api_error(self, mock_create_completion):
        mock_create_completion.side_effect = Exception("OpenAI API Error")

        product_data = {
            "nombre": "Test Product", "marca": "Test Brand", "precio": "10",
            "tecnologia": "Test Tech", "descripcion": "Test Desc",
            "ingredientes": ["i1", "i2"], "beneficios": ["b1", "b2"],
            "tipo_piel": "All", "estudios_clinicos": "None", "sostenibilidad": "Good"
        }
        with self.assertRaises(Exception) as context:
            bbbot.generate_newsletter(product_data)

        self.assertTrue("OpenAI API Error" in str(context.exception))

class TestBBBotSendEmail(unittest.TestCase):

    @patch('bbbot.smtplib.SMTP')
    @patch('bbbot.EMAIL_SENDER', 'sender@example.com')
    @patch('bbbot.EMAIL_RECEIVER', 'receiver@example.com')
    @patch('bbbot.SMTP_SERVER', 'smtp.example.com')
    @patch('bbbot.SMTP_PORT', 587)
    @patch('bbbot.SMTP_PASS', 'password')
    def test_send_email_success(self, mock_smtp_constructor):
        mock_smtp_instance = MagicMock()
        mock_smtp_constructor.return_value.__enter__.return_value = mock_smtp_instance # For 'with' statement

        subject = "Test Subject"
        body = "Test Body"
        product_url = "http://example.com/product"

        bbbot.send_email(subject, body, product_url)

        mock_smtp_constructor.assert_called_with('smtp.example.com', 587, timeout=30)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_with('sender@example.com', 'password')
        mock_smtp_instance.sendmail.assert_called_once()
        # Could add more assertions about the content of sendmail if needed

    @patch('bbbot.smtplib.SMTP')
    @patch('bbbot.EMAIL_SENDER', 'sender@example.com')
    @patch('bbbot.EMAIL_RECEIVER', 'receiver@example.com')
    @patch('bbbot.SMTP_SERVER', 'smtp.example.com')
    @patch('bbbot.SMTP_PORT', 587)
    @patch('bbbot.SMTP_PASS', 'password')
    def test_send_email_smtp_error(self, mock_smtp_constructor):
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, "Auth failed")
        mock_smtp_constructor.return_value.__enter__.return_value = mock_smtp_instance

        with self.assertRaises(smtplib.SMTPAuthenticationError):
            bbbot.send_email("Subject", "Body", "url")

if __name__ == '__main__':
    unittest.main()
