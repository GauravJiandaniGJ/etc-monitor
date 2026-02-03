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
            
            # Smart model discovery (matching AIParser logic)
            available_models = []
            try:
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        # Store both full name (models/gemini-pro) and short name (gemini-pro)
                        available_models.append(m.name)
                        short_name = m.name.split('/')[-1] if '/' in m.name else m.name
                        available_models.append(short_name)
            except Exception as e:
                logger.warning(f"Failed to list models: {e}")

            # Prioritize configured model, then specific stable models
            models_to_check = [model]
            # Add known stable models as fallbacks
            stable_fallbacks = [
                'models/gemini-2.5-flash', 'gemini-2.5-flash',
                'models/gemini-1.5-flash', 'gemini-1.5-flash',
                'models/gemini-pro', 'gemini-pro'
            ]
            for fb in stable_fallbacks:
                if fb not in models_to_check:
                    models_to_check.append(fb)
            
            # Add any other available models
            for av in available_models:
                if av not in models_to_check:
                    models_to_check.append(av)

            # Initialize with first working model
            working_client = None
            working_model_name = None

            for m_name in models_to_check:
                try:
                    # If we listed models, skip ones we know aren't there (optimization)
                    if available_models and m_name not in available_models:
                        # Except if it's the user configured one, give it a try regardless
                        if m_name != model:
                            continue

                    logger.debug(f'Trying to initialize Gemini with model: {m_name}')
                    client = genai.GenerativeModel(
                        model_name=m_name,
                        generation_config={
                            'temperature': temperature,
                            'max_output_tokens': 2048,
                        }
                    )
                    # Quick test? No, let's just assume init works if no exception.
                    # Actual generation test is done in test_connection()
                    working_client = client
                    working_model_name = m_name
                    logger.success(f'Gemini service initialized with model: {m_name}')
                    break
                except Exception as e:
                    logger.debug(f'Failed to init model {m_name}: {e}')
                    continue
            
            if working_client:
                self.client = working_client
                self.model = working_model_name
            else:
                logger.error('Failed to initialize Gemini service with any model')
                self.client = None

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
        """Generate text using Gemini AI with fallback logic.
        
        Tries multiple models if the primary one fails (404, 429, etc).
        
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
        
        # List of models to try in order
        models_to_try = [self.model]
        # Add fallbacks 
        fallbacks = ['models/gemini-2.5-flash', 'gemini-2.5-flash', 'models/gemini-1.5-flash', 'gemini-1.5-flash', 'models/gemini-pro']
        for fb in fallbacks:
            if fb not in models_to_try:
                models_to_try.append(fb)
        
        last_error = None
        
        # Try each model in sequence
        for model_name in models_to_try:
            try:
                # Re-configure client if model changes (except for first attempt which uses self.client)
                current_client = self.client
                if model_name != self.model or current_client is None:
                    try:
                        import google.generativeai as genai
                        current_client = genai.GenerativeModel(
                            model_name=model_name,
                            generation_config={
                                'temperature': gen_temperature,
                                'max_output_tokens': gen_max_tokens,
                            }
                        )
                    except Exception as e:
                        logger.warning(f'Failed to initialize model {model_name}: {e}')
                        continue

                # Retry loop for the CURRENT model
                # If we hit a 404 or 429, we break this loop and try the NEXT model immediately
                # We only retry the SAME model for generic network errors
                for attempt in range(self.max_retries):
                    try:
                        logger.debug(f'Generating with {model_name} (attempt {attempt + 1}/{self.max_retries})')
                        
                        response = current_client.generate_content(
                            prompt,
                            generation_config={
                                'temperature': gen_temperature,
                                'max_output_tokens': gen_max_tokens,
                            }
                        )
                        
                        if not response or not response.text:
                            logger.warning(f'Empty response from {model_name} (attempt {attempt + 1})')
                            if attempt < self.max_retries - 1:
                                self._wait_before_retry(attempt)
                                continue
                            else:
                                raise ValueError("Empty response after retries")
                        
                        result = response.text.strip()
                        logger.success(f'Generated {len(result)} characters with {model_name}')
                        
                        # If we switched models successfully, update the default for future calls
                        if model_name != self.model:
                            logger.info(f'Switching default model from {self.model} to {model_name}')
                            self.model = model_name
                            self.client = current_client
                            
                        return result
                        
                    except Exception as e:
                        error_str = str(e)
                        # Fail fast on specific errors
                        if "404" in error_str or "not found" in error_str.lower():
                            logger.warning(f'{model_name} not found (404), switching to next model...')
                            break # Break retry loop, go to next model
                        
                        if "429" in error_str or "quota" in error_str.lower():
                            logger.warning(f'{model_name} quota exceeded (429), switching to next model...')
                            break # Break retry loop, go to next model

                        logger.warning(f'{model_name} generation failed (attempt {attempt + 1}): {e}')
                        if attempt < self.max_retries - 1:
                            self._wait_before_retry(attempt)
                        else:
                            last_error = e
                            
            except Exception as e:
                logger.warning(f'Error with model {model_name}: {e}')
                last_error = e
                continue
                
        if last_error:
            logger.error(f'All models failed. Last error: {last_error}')
            
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
