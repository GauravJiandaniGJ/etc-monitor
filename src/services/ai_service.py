"""AI service for Gemini API integration.

Provides a service wrapper around Gemini AI with retry logic
and error handling.
"""
import time
from typing import Optional
from src.utils.logger import get_logger


logger = get_logger('GeminiService')


# Check if Gemini is available
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning('google-generativeai not installed. AI services will not be available.')


class GeminiService:
    """Service wrapper for Gemini AI.
    
    Provides generation capabilities with retry logic and error handling.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = 'gemini-1.5-flash',
        temperature: float = 0.2,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """Initialize Gemini service.
        
        Args:
            api_key: Gemini API key
            model: Gemini model name
            temperature: Generation temperature (0.0-2.0)
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (seconds)
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client = None
        
        if not GEMINI_AVAILABLE:
            logger.info('Gemini package not available')
            return
        
        if not api_key:
            logger.info('Gemini API key not configured')
            return
        
        try:
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(
                model_name=model,
                generation_config={
                    'temperature': temperature,
                    'max_output_tokens': 2048,
                }
            )
            logger.success(f'Gemini service initialized with model: {model}')
        except Exception as e:
            logger.error('Failed to initialize Gemini service', exc=e)
            self.client = None
    
    def is_configured(self) -> bool:
        """Check if Gemini service is configured and available.
        
        Returns:
            True if Gemini client is ready to use
        """
        return self.client is not None
    
    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[str]:
        """Generate text using Gemini AI with retry logic.
        
        Implements exponential backoff retry strategy for reliability.
        
        Args:
            prompt: Input prompt for generation
            temperature: Optional temperature override
            max_tokens: Optional max tokens override
            
        Returns:
            Generated text or None if generation fails
        """
        if not self.is_configured():
            logger.debug('Gemini service not configured')
            return None
        
        if not prompt:
            logger.warning('Empty prompt provided')
            return None
        
        # Use provided values or fall back to instance defaults
        gen_temperature = temperature if temperature is not None else self.temperature
        gen_max_tokens = max_tokens if max_tokens is not None else 2048
        
        # Retry loop with exponential backoff
        for attempt in range(self.max_retries):
            try:
                logger.debug(f'Generating with Gemini (attempt {attempt + 1}/{self.max_retries})')
                
                response = self.client.generate_content(
                    prompt,
                    generation_config={
                        'temperature': gen_temperature,
                        'max_output_tokens': gen_max_tokens,
                    }
                )
                
                if not response or not response.text:
                    logger.warning(f'Empty response from Gemini (attempt {attempt + 1})')
                    if attempt < self.max_retries - 1:
                        self._wait_before_retry(attempt)
                        continue
                    return None
                
                result = response.text.strip()
                logger.success(f'Generated {len(result)} characters')
                return result
                
            except Exception as e:
                logger.error(f'Gemini generation failed (attempt {attempt + 1})', exc=e)
                
                if attempt < self.max_retries - 1:
                    self._wait_before_retry(attempt)
                else:
                    logger.error('All retry attempts exhausted')
                    return None
        
        return None
    
    def _wait_before_retry(self, attempt: int):
        """Wait before retrying with exponential backoff.
        
        Args:
            attempt: Current attempt number (0-indexed)
        """
        delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
        logger.info(f'Waiting {delay:.1f} seconds before retry')
        time.sleep(delay)
    
    def test_connection(self) -> bool:
        """Test Gemini API connection.
        
        Sends a simple test prompt to verify the API is working.
        
        Returns:
            True if connection is successful
        """
        if not self.is_configured():
            return False
        
        try:
            result = self.generate('Test: Respond with "OK"', temperature=0.0)
            if result:
                logger.success('Gemini API connection test successful')
                return True
            else:
                logger.warning('Gemini API connection test failed: empty response')
                return False
        except Exception as e:
            logger.error('Gemini API connection test failed', exc=e)
            return False
    
    def rephrase_task(self, task_text: str) -> Optional[str]:
        """Rephrase a task message into a concise single sentence.

        Uses Gemini to summarize and rephrase task messages for better readability.

        Args:
            task_text: Original task message text

        Returns:
            Rephrased task as single sentence, or original text if rephrasing fails
        """
        if not task_text:
            return None

        prompt = f"""Rephrase the following task message into a clear, concise single sentence summary.
Keep it professional and actionable. Maximum 15 words.

Task: {task_text}

Rephrased (single sentence, max 15 words):"""

        rephrased = self.generate(prompt, temperature=0.3, max_tokens=100)

        if rephrased:
            # Clean up the response - remove extra quotes, whitespace
            rephrased = rephrased.strip().strip('"').strip("'")
            logger.success(f'Rephrased task: "{task_text[:50]}..." -> "{rephrased}"')
            return rephrased
        else:
            logger.warning('Failed to rephrase task, using original text')
            return task_text

    def get_model_info(self) -> dict:
        """Get information about the configured model.
        
        Returns:
            Dictionary with model configuration info
        """
        return {
            'model': self.model,
            'temperature': self.temperature,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'is_configured': self.is_configured(),
            'api_key_set': self.api_key is not None
        }
