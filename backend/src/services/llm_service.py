"""
LLM API Service Module

Provides interaction functionality with Large Language Model APIs, including text summarization, Q&A, etc.
Supports OpenAI API (with proxy).
"""

import os
import logging
import time
from typing import Optional, Dict, Any, Generator, List
from openai import OpenAI
import httpx

# ============================================================
# Shared Prompt Constants (used by multiple extraction methods)
# ============================================================

# Case type classification rules
DTYPE_RULES = """Emergency: Immediate threat to life/property (collapse, fallen trees on roads/buildings)
Urgent: Potential safety risk (hazardous trees, slope cracks >=5cm, blocked drainage)
General: No safety risk (grass cutting, scattered debris)
Adjust: Escalate for high-risk areas (hospitals, schools, major roads); downgrade for remote/unused slopes; prioritize Emergency during typhoon/heavy rain."""

# Subject matter categories for J_subject_matter field
SUBJECT_MATTER_CATEGORIES = """Hazardous Tree: pest/decay/aging issues
Tree Trimming/Pruning: pruning needs
Fallen Tree: loose/toppled trees
Grass Cutting: overgrown grass
Surface Erosion: slope surface damage
Others: other issues (beehives, work suspension, etc.)
Use & for multiple categories."""

# R_AI_Summary requirements
SUMMARY_REQUIREMENTS = """Generate R_AI_Summary (max 150 words) including:
1) case type, 2) caller name, 3) caller department, 4) call-in date,
5) key location, 6) specific incident, 7) departments involved,
8) whether falls under slope/tree maintenance, 9) duration (open to end/now)."""


class LLMService:
    """
    LLM API Service Class
    
    Provides interaction functionality with Large Language Model APIs, including text summarization, Q&A, etc.
    Supports OpenAI API (with proxy).
    """
    
    def __init__(self, api_key: str, provider: str = "openai", proxy_url: str = None, use_proxy: bool = False):
        """
        Initialize LLM Service
        
        Args:
            api_key: API key
            provider: API provider, "openai" (default: "openai")
            proxy_url: Proxy URL (e.g., "http://127.0.0.1:7890")
            use_proxy: Whether to use proxy (default: False)
        """
        self.api_key = api_key
        self.provider = provider
        self.proxy_url = proxy_url
        self.use_proxy = use_proxy
        self.logger = logging.getLogger(__name__)
        
        # Ensure logger level matches root logger for debug visibility
        root_logger = logging.getLogger()
        if root_logger.level <= logging.DEBUG:
            self.logger.setLevel(logging.DEBUG)
        
        # Validate API key
        if not self.api_key:
            self.logger.warning("⚠️ API key not set, AI summarization will be unavailable")
            self.client = None
        else:
            # Initialize client based on provider
            try:
                if provider == "openai":
                    # NOTE:
                    #   We intentionally do NOT pass any custom `proxies` argument here,
                    #   because that can conflict with the versions of `openai` / `httpx`
                    #   installed and lead to errors like:
                    #       Client.__init__() got an unexpected keyword argument 'proxies'
                    #
                    #   Instead, we:
                    #   - Log the detected httpx version (to help debug env issues)
                    #   - Rely on environment variables (HTTP_PROXY/HTTPS_PROXY, etc.)
                    #     or OpenAI's own configuration for proxy handling.
                    try:
                        self.logger.info(f"ℹ️ Using httpx version: {httpx.__version__}")
                    except Exception:
                        # Best-effort logging only
                        pass

                    # configure timeout settings (connect timeout: 30s, read timeout: 60s)
                    timeout = httpx.Timeout(30.0, read=60.0, connect=30.0)
                    
                    # check for proxy configuration from environment variables or parameters
                    proxy_url_configured = None
                    
                    # Priority 1: Check environment variables (HTTPS_PROXY or HTTP_PROXY)
                    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
                    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
                    
                    if https_proxy:
                        proxy_url_configured = https_proxy
                        self.logger.info(f"🌐 Detected HTTPS_PROXY from environment: {https_proxy}")
                    elif http_proxy:
                        proxy_url_configured = http_proxy
                        self.logger.info(f"🌐 Detected HTTP_PROXY from environment: {http_proxy}")
                    
                    # Priority 2: Use proxy_url parameter if provided
                    if not proxy_url_configured and use_proxy and proxy_url:
                        proxy_url_configured = proxy_url
                        self.logger.info(f"🌐 Using proxy from parameter: {proxy_url}")
                    
                    # create custom http_client with timeout configuration
                    # httpx automatically reads proxy from environment variables when trust_env=True (default)
                    # We rely on environment variables (HTTPS_PROXY/HTTP_PROXY) for proxy configuration
                    http_client = httpx.Client(
                        timeout=timeout,
                        trust_env=True  # Allow reading proxy from environment variables
                    )
                    
                    if proxy_url_configured:
                        self.logger.info(f"✅ HTTP client configured with proxy from environment: {proxy_url_configured}")
                    else:
                        # Check if proxy is in environment
                        env_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
                        if env_proxy:
                            self.logger.info(f"✅ HTTP client will use proxy from environment variable: {env_proxy}")
                        else:
                            self.logger.info("ℹ️ HTTP client configured for direct connection (no proxy)")
                    
                    # use custom http_client to configure timeout and proxy
                    # Note: OpenAI SDK automatically sets the following headers:
                    # - Authorization: Bearer {api_key} (from api_key parameter)
                    # - Content-Type: application/json (automatically set by SDK)
                    self.client = OpenAI(
                        api_key=self.api_key,
                        http_client=http_client
                    )
                    
                    # Log API key status (masked for security)
                    api_key_preview = f"{self.api_key[:7]}...{self.api_key[-4:]}" if len(self.api_key) > 11 else "***"
                    self.logger.info(f"✅ OpenAI LLM client initialized successfully")
                    self.logger.debug(f"   - API Key: {api_key_preview}")
                    self.logger.debug(f"   - Headers: Authorization (Bearer) and Content-Type (application/json) are auto-configured")
                    self.logger.info(f"   - Timeout settings: connect=30s, read=60s")
                else:
                    self.logger.error(f"❌ Unknown provider: {provider}. Only 'openai' is supported.")
                    self.client = None
            except Exception as e:
                self.logger.error(f"❌ LLM client initialization failed: {e}")
                self.client = None

        # Ollama client is created lazily when provider is ollama (per-request)
        self._ollama_client = None

    def _get_ollama_client(self):
        """Lazy-create and cache OpenAI-compatible client for Ollama."""
        if self._ollama_client is not None:
            return self._ollama_client
        try:
            from config.settings import OLLAMA_BASE_URL
            base_url = f"{OLLAMA_BASE_URL.rstrip('/')}/v1"
            self._ollama_client = OpenAI(base_url=base_url, api_key="ollama")
            self.logger.info(f"✅ Ollama LLM client initialized: {base_url}")
            return self._ollama_client
        except Exception as e:
            self.logger.error(f"❌ Ollama client initialization failed: {e}")
            return None
    
    def summarize_text(
        self,
        text: str,
        max_length: int = 600,
        negative_example: Optional[str] = None,
    ) -> Optional[str]:
        """
        Use LLM API to summarize text in one sentence

        Args:
            text: Text to be summarized
            max_length: Maximum length of the summary
            negative_example: Optional prior output to avoid (for faithfulness repair)

        Returns:
            Summary result, returns None on failure
        """
        try:
            # Check API key and client
            if not self.api_key or not self.client:
                self.logger.warning("⚠️ API key not set or client not initialized, cannot generate AI summary")
                return None

            # Validate input text
            if text is None:
                self.logger.warning("⚠️ None text provided for summarization")
                return None

            if not isinstance(text, str):
                self.logger.error(f"❌ Invalid text type: {type(text)}, expected str")
                return None

            if not text.strip():
                self.logger.warning("⚠️ Empty or whitespace-only text provided for summarization")
                return None

            # Build request message (use single line string to avoid whitespace problem)
            text_snippet = text[:9000] if len(text) > 9000 else text
            neg_block = ""
            if negative_example and negative_example.strip():
                neg_block = (
                    "\n\nIMPORTANT: Do NOT produce a summary like the following (it was deemed unfaithful):\n"
                    f"{negative_example.strip()[:500]}\n\n"
                    "Produce a different, more faithful summary."
                )
            message = (
                "Summarize the following text into a single fluent English sentence (max 150 words). "
                "The summary must include: "
                "1) case type, "
                "2) caller name, "
                "3) caller department, "
                "4) call-in date, "
                "5) key location, "
                "6) number of departments involved (infer if unclear), "
                "7) whether it falls under the slope and tree maintenance department, "
                "8) duration: from case open date to end date (or to now if missing). "
                "If information is unclear, infer cautiously from context. "
                f"{neg_block}\n\nHere is the text: {text_snippet}"
            )
            
            # Call API based on provider
            if self.provider == "openai":
                # 配置重试参数
                max_retries = 3
                retry_delay = 2  # initial delay 2 seconds
                
                for attempt in range(1, max_retries + 1):
                    try:
                        self.logger.info(f"🔄 Attempting OpenAI API call (attempt {attempt}/{max_retries})...")
                        
                        # API call to OpenAI
                        # Note: The following HTTP headers are automatically set by OpenAI SDK:
                        # - Authorization: Bearer {api_key} (from client initialization)
                        # - Content-Type: application/json (automatically set)
                        # These do not need to be manually specified in the API call.
                        response = self.client.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You are an expert case-log extraction assistant. You must interpret messy, noisy text logs and extract structured information reliably."
                                },
                                {
                                    "role": "user",
                                    "content": message
                                }
                            ],
                            max_tokens=300,
                            temperature=0.3
                        )
                        
                        # Extract response content
                        if response and response.choices and len(response.choices) > 0:
                            content = response.choices[0].message.content
                            if content and content.strip():
                                self.logger.info("✅ OpenAI AI summary generated successfully")
                                return content.strip()
                        
                        self.logger.warning("⚠️ API response is empty or invalid")
                        return None
                        
                    except Exception as api_error:
                        error_type = type(api_error).__name__
                        error_msg = str(api_error)
                        
                        # check if it is a timeout error or retryable error
                        is_timeout_error = "timeout" in error_msg.lower() or "APITimeoutError" in error_type
                        is_retryable = is_timeout_error or "rate limit" in error_msg.lower() or "503" in error_msg or "502" in error_msg
                        
                        if is_retryable and attempt < max_retries:
                            # calculate backoff delay (exponential backoff)
                            delay = retry_delay * (2 ** (attempt - 1))
                            self.logger.warning(
                                f"⚠️ OpenAI API call failed (attempt {attempt}/{max_retries}): {error_type} - {error_msg}. "
                                f"Retrying in {delay} seconds..."
                            )
                            time.sleep(delay)
                            continue
                        else:
                            # non-retryable error or maximum retry attempts reached
                            self.logger.error(f"❌ OpenAI API call failed after {attempt} attempt(s): {error_type} - {error_msg}")
                            
                            # log more detailed error information
                            import traceback
                            if is_timeout_error:
                                self.logger.error(
                                    "⏱️ Request timed out. This might be due to:\n"
                                    "  - Slow network connection\n"
                                    "  - OpenAI API server issues\n"
                                    "  - Request payload too large\n"
                                    "Consider reducing the input text length or checking your network connection."
                                )
                            self.logger.debug(f"Full traceback:\n{traceback.format_exc()}")
                            
                            return None
            else:
                self.logger.warning(f"⚠️ Unsupported provider: {self.provider}. Only 'openai' is supported.")
                return None
            
            self.logger.warning("⚠️ API response is empty or invalid")
            return None
            
        except Exception as e:
            # catch all other exceptions
            error_type = type(e).__name__
            error_msg = str(e)
            self.logger.error(f"❌ AI summary generation failed: {error_type} - {error_msg}")
            
            # log full stack trace for debugging
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
            return None

    def summarize_file(self, file_path: str, max_length: int = 100) -> Optional[str]:
        """
        Use LLM API to summarize file
        
        Args:
            file_path: File path
            max_length: Maximum length of summary
            
        Returns:
            Summary result, returns None on failure
        """
        try:
            # Check API key and client
            if not self.api_key or not self.client:
                self.logger.warning("⚠️ API key not set or client not initialized, cannot generate AI summary")
                return None
            
            # Extract content based on file type
            file_content = self._extract_file_content(file_path)
            if not file_content:
                self.logger.error(f"❌ Unable to extract file content: {file_path}")
                return None
            
            # Call text summarization method
            return self.summarize_text(file_content, max_length)
            
        except Exception as e:
            self.logger.error(f"❌ File summarization processing exception: {e}")
            return None

    def summarize_text_stream(self, text: str, max_length: int = 600) -> Generator[str, None, None]:
        """
        Use LLM API to summarize text, streaming tokens.
        Same prompt as summarize_text; yields content deltas.
        """
        try:
            if not self.api_key or not self.client:
                self.logger.warning("⚠️ API key or client not set, cannot stream AI summary")
                return
            if text is None or not isinstance(text, str) or not text.strip():
                return
            text_snippet = text[:9000] if len(text) > 9000 else text
            message = (
                "Summarize the following text into a single fluent English sentence (max 150 words). "
                "The summary must include: "
                "1) case type, "
                "2) caller name, "
                "3) caller department, "
                "4) call-in date, "
                "5) key location, "
                "6) number of departments involved (infer if unclear), "
                "7) whether it falls under the slope and tree maintenance department, "
                "8) duration: from case open date to end date (or to now if missing). "
                "If information is unclear, infer cautiously from context. "
                f"Here is the text: {text_snippet}"
            )
            if self.provider != "openai":
                return
            self.logger.info("🔄 Calling OpenAI API for summary (stream)...")
            stream = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert case-log extraction assistant. You must interpret messy, noisy text logs and extract structured information reliably."},
                    {"role": "user", "content": message}
                ],
                max_tokens=300,
                temperature=0.3,
                stream=True
            )
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if getattr(delta, "content", None):
                        yield delta.content
            self.logger.info("✅ Summary stream completed")
        except Exception as e:
            self.logger.error(f"❌ Summary stream failed: {type(e).__name__} - {e}")
            raise

    def summarize_file_stream(self, file_path: str, max_length: int = 100) -> Generator[str, None, None]:
        """Stream summary from file content via summarize_text_stream."""
        try:
            if not self.api_key or not self.client:
                return
            file_content = self._extract_file_content(file_path)
            if not file_content:
                return
            yield from self.summarize_text_stream(file_content, max_length)
        except Exception as e:
            self.logger.error(f"❌ File summary stream failed: {e}")
            raise
    
    def _extract_file_content(self, file_path: str) -> Optional[str]:
        """
        Extract content based on file type
        
        Args:
            file_path: File path (can be relative or absolute)
            
        Returns:
            File content, returns None on failure
        """
        try:
            # Handle file paths that may contain special characters like #
            # Ensure the path is properly handled (no URL decoding needed for file paths)
            original_path = file_path
            
            # Convert to absolute path for reliable checking
            # Note: os.path.abspath handles # correctly, but we need to ensure
            # the path hasn't been URL-decoded incorrectly
            abs_file_path = os.path.abspath(file_path)
            
            # Log path information for debugging
            self.logger.debug(f"📄 Extracting content from file:")
            self.logger.debug(f"   Original path: {original_path}")
            self.logger.debug(f"   Absolute path: {abs_file_path}")
            self.logger.debug(f"   File exists: {os.path.exists(abs_file_path)}")
            
            if not os.path.exists(abs_file_path):
                # Try to find the file in common temp directories
                # Sometimes the file might be in a different location
                temp_dirs = ['/tmp', '/var/tmp', os.path.join(os.getcwd(), 'temp')]
                found_alternative = False
                
                for temp_dir in temp_dirs:
                    if os.path.exists(temp_dir):
                        # Try to find file by basename in temp directory
                        basename = os.path.basename(file_path)
                        alt_path = os.path.join(temp_dir, basename)
                        if os.path.exists(alt_path):
                            self.logger.info(f"✅ Found file in alternative location: {alt_path}")
                            abs_file_path = alt_path
                            found_alternative = True
                            break
                
                if not found_alternative:
                    self.logger.error(f"❌ File does not exist: {abs_file_path}")
                    self.logger.error(f"   Original path: {original_path}")
                    self.logger.error(f"   Current working directory: {os.getcwd()}")
                    # List files in the directory if it exists
                    dir_path = os.path.dirname(abs_file_path)
                    if os.path.exists(dir_path):
                        try:
                            files_in_dir = os.listdir(dir_path)
                            self.logger.error(f"   Files in directory: {files_in_dir[:10]}")  # Show first 10 files
                        except Exception as e:
                            self.logger.error(f"   Cannot list directory: {e}")
                    return None
            
            if not os.path.isfile(abs_file_path):
                self.logger.error(f"❌ Path is not a file: {abs_file_path}")
                return None
            
            # Use absolute path for further processing
            file_path = abs_file_path
            
            file_extension = os.path.splitext(file_path)[1].lower()
            # Log debug info - will show if LOG_LEVEL=DEBUG is set
            self.logger.debug(f"📄 Processing file: {file_path}, type: {file_extension}")
            # Also print for immediate visibility in development
            print(f"📄 Processing file: {os.path.basename(file_path)}, type: {file_extension}", flush=True)
            
            if file_extension == '.txt':
                # Process text file
                return self._extract_txt_content(file_path)
                
            elif file_extension == '.pdf':
                # Process PDF file
                return self._extract_pdf_content(file_path)
                
            else:
                self.logger.warning(f"⚠️ Unsupported file type: {file_extension} for file: {file_path}")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ File content extraction exception: {e}")
            self.logger.error(f"   File path: {file_path}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
    
    def _extract_txt_content(self, file_path: str) -> Optional[str]:
        """
        Extract TXT file content
        
        Args:
            file_path: TXT file path
            
        Returns:
            File content, returns None on failure
        """
        try:
            # NOTE:
            #   We intentionally use an absolute import here instead of a
            #   relative one (e.g. ``from ..utils...``), because ``services``
            #   is loaded as a namespace package when ``backend/src`` is added
            #   to ``sys.path`` (see ``main.py``). Using a relative import
            #   would fail if the package metadata is incomplete, which breaks
            #   AI summarization.
            from utils.file_utils import read_file_with_encoding
            return read_file_with_encoding(file_path)
        except Exception as e:
            self.logger.error(f"❌ TXT file content extraction failed: {e}")
            return None
    
    def _extract_pdf_content(self, file_path: str) -> Optional[str]:
        """
        Extract PDF file content for AI summarization.
        
        NOTE:
        - This method is intentionally kept lightweight and independent from the
          heavy OCR / business logic in `core.extractFromTMO` / `core.extractFromRCC`
          to avoid circular / fragile imports (which were causing
          "attempted relative import beyond top-level package" errors).
        - The main SRR extraction logic still uses those core modules; here we
          just need *some* text for the LLM to work with.
        """
        try:
            # First, try pdfplumber which usually gives the best text layout.
            try:
                import pdfplumber  # type: ignore
                text_parts = []
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)
                if text_parts:
                    return "\n".join(text_parts).strip()
            except Exception as e:
                self.logger.warning(f"⚠️ pdfplumber PDF extraction failed: {e}")
            
            # Fallback: basic PyPDF2 text extraction.
            try:
                import PyPDF2  # type: ignore
                text = ""
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                return text.strip() if text.strip() else None
            except Exception as e:
                self.logger.error(f"❌ PyPDF2 extraction failed: {e}")
                return None
        except Exception as e:
            self.logger.error(f"❌ PDF content extraction exception: {e}")
            return None

    def extract_fields_from_image(self, image_path: str, file_type: str) -> Optional[Dict[str, Any]]:
        """
        Use OpenAI Vision API to extract A-Q fields from PDF image
        
        Args:
            image_path: Path to the image file (PNG/JPEG)
            file_type: Type of file ("RCC" or "TMO") - must be explicitly specified
            
        Returns:
            Dictionary containing extracted A-Q fields, or None on failure
        """
        try:
            # Check API key and client
            if not self.api_key or not self.client:
                self.logger.warning("⚠️ API key not set or client not initialized, cannot use Vision API")
                return None
            
            # Read image file and encode to base64
            import base64
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Determine file extension
            import os
            file_ext = os.path.splitext(image_path)[1].lower()
            if file_ext == '.png':
                image_format = "image/png"
            elif file_ext in ['.jpg', '.jpeg']:
                image_format = "image/jpeg"
            else:
                self.logger.error(f"❌ Unsupported image format: {file_ext}")
                return None
            
            # Validate file type
            if file_type not in ["RCC", "TMO"]:
                self.logger.error(f"❌ Invalid file_type: {file_type}. Must be 'RCC' or 'TMO'")
                return None
            
            # Build optimized prompt for RCC/TMO documents
            doc_type_hint = "RCC" if file_type == "RCC" else "TMO"
            
            # Use shared constants for rules
            prompt = f"""Extract fields from this {doc_type_hint} document. Return JSON only.

FIELDS (use dd-MMM-yyyy for dates, empty string if not found):
- A_date_received: Date of Referral
- B_source: "{doc_type_hint}" (TMO for ASD PDF, RCC for RCC PDF)
- C_case_number: 1823 Case Number
- D_type: Emergency/Urgent/General
- E_caller_name: Caller/Inspection Officer name
- F_contact_no: Contact Number
- G_slope_no: Slope Number (e.g., 11SW-D/CR995, NOT with date suffix)
- H_location: Location/District
- I_nature_of_request: 2-20 word action phrase "[action] at [slope/treeID]"
- J_subject_matter: Category from rules below
- K_10day_rule_due_date: 10-day Rule Due Date
- L_icc_interim_due: ICC Interim Reply Due Date
- M_icc_final_due: ICC Final Reply Due Date
- N_works_completion_due: Works Completion Due Date
- O1_fax_to_contractor: Fax to Contractor Date
- O2_email_send_time: Email Send Time
- P_fax_pages: Fax Pages count
- Q_case_details: Case Details/Follow-up Actions
- R_AI_Summary: Max 150 words summary

CLASSIFICATION RULES:
D_type:
{DTYPE_RULES}

J_subject_matter:
{SUBJECT_MATTER_CATEGORIES}

SOURCE-SPECIFIC RULES:
TMO: E_caller_name=inspection officer name (e.g. "Hin LH HUI of TMO (DEVB)"), F_contact_no=phone number from "Contact" field (e.g. "3509 7662"), extract actual values from document
RCC: L_icc_interim_due="N/A", M_icc_final_due="N/A" (exactly, no extra text)
RCC: E_caller_name=complete name before "Contact Tel No." (2-3 uppercase letter words)

I_nature_of_request FORMAT:
Action phrase (2-20 words): [observe/repair/conduct/etc.] at [slope ID/treeID]
Examples: Fallen tree removal, Drainage Clearance, Grass Cutting, Water Seepage, Rock/Soil Movement, Dead Tree(s)

{SUMMARY_REQUIREMENTS}"""
            
            # Call OpenAI Vision API
            self.logger.info(f"🔄 Calling OpenAI Vision API for {file_type} document...")
            
            response = self.client.chat.completions.create(
                model="gpt-4o",  # Use gpt-4o for vision capabilities
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert document extraction assistant. Extract structured information from document images and return valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{image_format};base64,{image_data}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=2000,
                temperature=0.1  # Low temperature for accurate extraction
            )
            
            # Extract response content
            if response and response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content and content.strip():
                    # Parse JSON response
                    import json
                    # Remove markdown code blocks if present
                    content = content.strip()
                    if content.startswith("```json"):
                        content = content[7:]
                    elif content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()
                    
                    try:
                        extracted_data = json.loads(content)
                        self.logger.info(f"✅ Successfully extracted {len(extracted_data)} fields from {file_type} document")
                        return extracted_data
                    except json.JSONDecodeError as e:
                        self.logger.error(f"❌ Failed to parse JSON response: {e}")
                        self.logger.debug(f"Response content: {content}")
                        return None
            
            self.logger.warning("⚠️ Vision API response is empty or invalid")
            return None
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            self.logger.error(f"❌ Vision API extraction failed: {error_type} - {error_msg}")
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return None

    def chat_stream(
        self,
        query: str,
        context: str,
        raw_content: str,
        his_context: str,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Stream chat response chunks for SSE. Yields non-empty string chunks.
        provider: 'openai' | 'ollama'. model: model name (defaults per provider).
        """
        try:
            prov = (provider or self.provider or "openai").lower()
            if prov == "ollama":
                client = self._get_ollama_client()
                if not client:
                    self.logger.warning("⚠️ Ollama client not available")
                    return
                from config.settings import OLLAMA_CHAT_MODEL
                model_name = model or OLLAMA_CHAT_MODEL
                self.logger.info(f"🔄 Calling Ollama for chat (stream): {model_name}")
            else:
                client = self.client
                if not self.api_key or not client:
                    self.logger.warning("⚠️ API key not set or client not initialized, cannot use OpenAI API")
                    return
                model_name = model or "gpt-4o-mini"
                self.logger.info(f"🔄 Calling OpenAI API for chat (stream): {model_name}")

            prompt = f"""Answer the following question based on the provided context. Fabrication is prohibited.

IMPORTANT: The "Raw Content" below is the FULL ORIGINAL DOCUMENT TEXT. It is the PRIMARY source for document-specific details such as assignment history, case details, and any content not explicitly listed in the structured fields. Always check Raw Content first when the user asks about document content (e.g. assignment history, case details, follow-up actions).

"Extracted structured data" contains fields A-Q. Q_case_details may include case details and assignment history. "History Context" contains similar historical cases and knowledge base references.

User Question: {query}

Extracted structured data: {context}

Raw Content (full original document - check this for assignment history and case details): {raw_content if raw_content else "(empty - use Extracted structured data, especially Q_case_details)"}

History Context: {his_context}

Requirements: concise, accurate, in line with actual processing procedures. If Raw Content is provided, use it to answer document-specific questions.
Default response language: English. Only switch language if the user explicitly requests a different language.
Do your reasoning internally and provide only the final answer with clear evidence-based statements.
            """
            stream = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant that can answer questions based on the provided context. "
                            "Reply in English by default unless the user explicitly asks for another language."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=2000,
                temperature=0.1,
                stream=True,
            )
            for chunk in stream:
                if not chunk or not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and getattr(delta, "content", None):
                    yield delta.content
        except Exception as e:
            self.logger.error(f"❌ Chat stream failed: {type(e).__name__} - {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            yield ""

    def extract_fields_from_text(
        self,
        text_content: str,
        email_content: str = None,
        correction_hints: Optional[List[Dict[str, str]]] = None,
        few_shot_examples: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Use OpenAI API to extract A-Q fields from TXT content

        Args:
            text_content: TXT file content
            email_content: Optional email content for additional context
            correction_hints: Optional list of past user corrections to inject into prompt
            few_shot_examples: Optional list of similar historical cases (A-Q-like dicts) for few-shot

        Returns:
            Dictionary containing extracted A-Q fields, or None on failure
        """
        try:
            # Check API key and client
            if not self.api_key or not self.client:
                self.logger.warning("⚠️ API key not set or client not initialized, cannot use OpenAI API")
                return None

            # Combine text and email content if available
            full_content = text_content
            if email_content:
                full_content = f"Main Content:\n{text_content}\n\nEmail Content:\n{email_content}"

            # Limit content length to avoid token limits (keep first 8000 characters)
            if len(full_content) > 8000:
                full_content = full_content[:8000] + "\n\n[... content truncated ...]"

            correction_block = ""
            if correction_hints:
                lines = [
                    f"- {h.get('field', '')}: 错误值 '{h.get('incorrect', '')}' 应改为 '{h.get('correct', '')}'"
                    + (f" ({h.get('note', '')})" if h.get('note') else "")
                    for h in correction_hints
                ]
                correction_block = (
                    "\n\nIMPORTANT - Past user corrections (apply when applicable):\n"
                    + "\n".join(lines)
                )

            schema_block = ""
            try:
                from utils.field_schema import schema_to_llm_prompt_block
                schema_block = schema_to_llm_prompt_block(
                    include_classification=False,
                )
                if schema_block:
                    schema_block = "\n\nSchema reference:\n" + schema_block
            except Exception:
                pass

            few_shot_block = ""
            if few_shot_examples and len(few_shot_examples) > 0:
                lines = []
                for i, ex in enumerate(few_shot_examples[:5], 1):
                    if isinstance(ex, dict) and ex:
                        parts = [f"Example {i}: "]
                        for k, v in ex.items():
                            if v not in (None, "", [], {}):
                                parts.append(f"  {k}={repr(v)[:80]}")
                        lines.append("\n".join(parts))
                if lines:
                    few_shot_block = "\n\nSimilar past cases (use as reference for field format):\n" + "\n\n".join(lines)

            # Build optimized prompt for TXT extraction (uses shared constants)
            prompt = f"""Extract fields from ICC case file. Return JSON only.

CRITICAL - A_date_received (HIGHEST PRIORITY):
Find section "II. ASSIGNMENT HISTORY:" which contains a table like:
[Date/Time]         [Status]      [Dept]   [Assigned To]
<datetime_1>        Misassigned   HYD      HYDM(...)
<datetime_2>        Open          ASD      Property Services Branch

EXTRACT: The [Date/Time] from the row where [Status]="Open" AND [Dept]="ASD"
Format conversion: "YYYY-MM-DD HH:MM:SS" -> "dd-MMM-yyyy" 

RULES:
- ONLY use this table, NEVER use "Case Creation Date" or other dates
- If multiple matching rows, use the FIRST one
- If no matching row, return empty string

CLASSIFICATION RULES:
D_type:
{DTYPE_RULES}

J_subject_matter (based on I_nature_of_request):
{SUBJECT_MATTER_CATEGORIES}

EXTRACTION RULES:
- B_source: "ICC" (this is a TXT file)
- E_caller_name: Last Name from "VI. CONTACT INFORMATION", "NA" if anonymous
- F_contact_no: From "VI. CONTACT INFORMATION" section:
  * If both Mobile and Email have values: "Mobile / Email"
  * If only Mobile has value: use Mobile only
  * If only Email has value: use Email only
  * If both empty (anonymous): "NA"
- L_icc_interim_due: [Interim Reply] from "I. DUE DATE:" section
- M_icc_final_due: [Final Reply] from "I. DUE DATE:" section
- Do NOT invent, guess, or hallucinate values

{SUMMARY_REQUIREMENTS}

Return valid JSON only (empty string if not found, dd-MMM-yyyy for dates) with these exact keys:
A_date_received, B_source, C_case_number, D_type, E_caller_name, F_contact_no,
G_slope_no, H_location, I_nature_of_request, J_subject_matter, K_10day_rule_due_date,
L_icc_interim_due, M_icc_final_due, N_works_completion_due, O1_fax_to_contractor,
O2_email_send_time, P_fax_pages, Q_case_details, R_AI_Summary
{correction_block}
{schema_block}
{few_shot_block}
"""

            # Call OpenAI API
            self.logger.info("🔄 Calling OpenAI API for TXT document extraction...")
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Use gpt-4o-mini for text extraction (cost-effective)
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert case data extraction assistant. Extract structured information from case file text content and return valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": f"{prompt}\n\nText Content:\n{full_content}"
                    }
                ],
                max_tokens=2000,
                temperature=0,  # Low temperature for accurate extraction
                top_p=1
            )
            
            # Extract response content
            if response and response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content and content.strip():
                    # Parse JSON response
                    import json
                    # Remove markdown code blocks if present
                    content = content.strip()
                    if content.startswith("```json"):
                        content = content[7:]
                    elif content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    content = content.strip()
                    
                    try:
                        extracted_data = json.loads(content)
                        self.logger.info(f"✅ Successfully extracted {len(extracted_data)} fields from TXT document")
                        return extracted_data
                    except json.JSONDecodeError as e:
                        self.logger.error(f"❌ Failed to parse JSON response: {e}")
                        self.logger.debug(f"Response content: {content}")
                        return None
            
            self.logger.warning("⚠️ OpenAI API response is empty or invalid")
            return None
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            self.logger.error(f"❌ Text extraction failed: {error_type} - {error_msg}")
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return None

    def generate_reply_draft(
        self,
        reply_type: str,
        case_data: dict,
        template_content: str,
        conversation_history: list,
        user_message: str = None,
        language: str = 'zh',
        is_initial: bool = False,
        skip_questions: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        生成回复草稿或询问补充信息
        
        Args:
            reply_type: 回复类型 (interim, final, wrong_referral)
            case_data: 案件数据字典
            template_content: 模板示例库内容
            conversation_history: 对话历史列表
            user_message: 用户当前消息
            language: 语言代码 (zh/en)
            is_initial: 是否为初次请求
            skip_questions: 是否跳过询问直接生成
        
        Returns:
            字典包含:
            - is_question: 是否为询问
            - message: AI消息内容
            - draft_reply: 草稿回复（如已生成）
        """
        try:
            if not self.api_key or not self.client:
                self.logger.warning("⚠️ API key not set or client not initialized, cannot use OpenAI API")
                return None
            
            # 如果跳过询问，直接生成草稿
            if skip_questions:
                return self._generate_draft_reply(
                    reply_type, case_data, template_content, 
                    [], "", language  # 空的对话历史和用户消息
                )
            
            # 阶段1：初次请求，生成询问问题
            if is_initial:
                return self._generate_initial_question(reply_type, case_data, language)
            
            # 阶段2：生成草稿回复
            return self._generate_draft_reply(
                reply_type, case_data, template_content, 
                conversation_history, user_message, language
            )
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            self.logger.error(f"❌ Reply draft generation failed: {error_type} - {error_msg}")
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return None

    def _resolve_reply_deadline(self, reply_type: str, case_data: Dict[str, Any]) -> str:
        if reply_type == "interim":
            return (
                str(case_data.get("L_icc_interim_due") or "").strip()
                or str(case_data.get("K_10day_rule_due_date") or "").strip()
                or "N/A"
            )
        if reply_type == "final":
            return (
                str(case_data.get("M_icc_final_due") or "").strip()
                or str(case_data.get("N_works_completion_due") or "").strip()
                or "N/A"
            )
        return str(case_data.get("K_10day_rule_due_date") or "").strip() or "N/A"

    def _build_reply_slip_selections(self, reply_type: str, case_data: Dict[str, Any]) -> Dict[str, List[str]]:
        ack_items: List[str] = ["Case receipt acknowledged"]
        if str(case_data.get("H_location") or "").strip():
            ack_items.append("Location identified")
        if str(case_data.get("G_slope_no") or "").strip():
            ack_items.append("Slope number referenced")

        int_items: List[str] = []
        if reply_type == "interim":
            int_items.append("Interim reply issued")
        elif reply_type == "final":
            int_items.append("Final reply issued")
        else:
            int_items.append("Wrong referral notice issued")

        subject = str(case_data.get("J_subject_matter") or "").strip() or "Others"
        case_type = str(case_data.get("D_type") or "").strip() or "General"
        sub_items = [
            f"Subject matter: {subject}",
            f"Case type: {case_type}",
        ]
        return {"ACK": ack_items, "INT": int_items, "SUB": sub_items}
    
    def _generate_initial_question(self, reply_type: str, case_data: dict, language: str) -> Dict[str, Any]:
        """生成初次询问问题（简化版，只询问案件数据中没有的关键信息）"""
        
        # 根据回复类型构建简化的询问提示
        questions_zh = {
            "interim": """您好！我将协助您草拟过渡回复。

            📋 已从案件中获取的信息：
            - 案件编号: {case_number}
            - 斜坡编号: {slope_no}
            - 位置: {location}
            - 事项类型: {subject_matter}

            请补充以下信息（可选）：
            1. 视察日期（如已进行）
            2. 计划完成日期或时间
            3. 其他补充说明""",
            "final": """您好！我将协助您草拟最终回复。

            📋 已从案件中获取的信息：
            - 案件编号: {case_number}
            - 斜坡编号: {slope_no}
            - 位置: {location}
            - 事项类型: {subject_matter}

            请补充以下信息（可选）：
            1. 完成工作的日期
            2. 具体完成的行动
            3. 其他补充说明""",
            "wrong_referral": """您好！我将协助您草拟错误转介回复。

            📋 已从案件中获取的信息：
            - 案件编号: {case_number}
            - 斜坡编号: {slope_no}
            - 位置: {location}

            请补充以下信息（必要）：
            1. 应转介的部门（如：LCSD康文署、HYD等）
            2. GLA编号（如已知）

            💡 提示：至少需要提供转介部门信息。"""
        }
        
        questions_en = {
            "interim": """Hello! I will assist you in drafting an Interim reply.

            📋 Information obtained from case:
            - Case Number: {case_number}
            - Slope No.: {slope_no}
            - Location: {location}
            - Subject Matter: {subject_matter}

            Please provide the following (optional):
            1. Inspection date (if conducted)
            2. Planned completion date
            3. Additional notes

            💡 Hint: If no supplement needed, type "none" or click the Direct button.""",
            "final": """Hello! I will assist you in drafting a Final reply.

            📋 Information obtained from case:
            - Case Number: {case_number}
            - Slope No.: {slope_no}
            - Location: {location}
            - Subject Matter: {subject_matter}

            Please provide the following (optional):
            1. Work completion date
            2. Actions completed
            3. Additional notes

            💡 Hint: If no supplement needed, type "none" or click the Direct button.""",
            "wrong_referral": """Hello! I will assist you in drafting a Wrong Referral reply.

            📋 Information obtained from case:
            - Case Number: {case_number}
            - Slope No.: {slope_no}
            - Location: {location}

            Please provide the following (required):
            1. Department to refer to (e.g., LCSD, HYD)
            2. GLA number (if known)

            💡 Tip: At least the referral department is required."""
        }
        
        # Choose language: default from API is 'en' for UI; can be 'zh' when user writes in Chinese
        questions = questions_zh if language == 'zh' else questions_en
        message_template = questions.get(reply_type, questions["interim"])
        
        # 填充案件信息
        message = message_template.format(
            case_number=case_data.get('C_case_number', 'N/A'),
            slope_no=case_data.get('G_slope_no', 'N/A'),
            location=case_data.get('H_location', 'N/A'),
            subject_matter=case_data.get('J_subject_matter', 'N/A')
        )
        
        return {
            "is_question": True,
            "message": message,
            "draft_reply": None,
            "reply_slip_selections": self._build_reply_slip_selections(reply_type, case_data),
            "deadline": self._resolve_reply_deadline(reply_type, case_data),
        }
    
    def _generate_draft_reply(
        self, reply_type: str, case_data: dict, template_content: str,
        conversation_history: list, user_message: str, language: str
    ) -> Dict[str, Any]:
        """生成草稿回复"""
        
        # 构建对话历史文本
        history_text = ""
        if conversation_history:
            for msg in conversation_history:
                role = msg.get('role', '')
                content = msg.get('content', '')
                history_text += f"{role}: {content}\n\n"
        
        # 如果没有用户消息，表示是直接生成模式
        if not user_message or user_message.strip().lower() in ['无', 'none', 'skip', '']:
            user_message = "请直接使用案件数据生成回复，无额外补充。" if language == 'zh' else "Please generate reply using case data directly, no additional information."
        
        # 构建案件信息
        case_info = f"""- Case Number: {case_data.get('C_case_number', 'N/A')}
        - Date Received: {case_data.get('A_date_received', 'N/A')}
        - Source: {case_data.get('B_source', 'N/A')}
        - Type: {case_data.get('D_type', 'N/A')}
        - Slope Number: {case_data.get('G_slope_no', 'N/A')}
        - Location: {case_data.get('H_location', 'N/A')}
        - Subject Matter: {case_data.get('J_subject_matter', 'N/A')}
        - Nature of Request: {case_data.get('I_nature_of_request', 'N/A')}
        - Caller: {case_data.get('E_caller_name', 'N/A')}
        - Contact: {case_data.get('F_contact_no', 'N/A')}
        - 10-day Due: {case_data.get('K_10day_rule_due_date', 'N/A')}
        - ICC Interim Due: {case_data.get('L_icc_interim_due', 'N/A')}
        - ICC Final Due: {case_data.get('M_icc_final_due', 'N/A')}"""
        
        # 构建prompt
        system_prompt = "You are an expert assistant for drafting official ArchSD SRR case replies. You have access to a template library containing multiple real-world examples."
        
        if language == 'zh':
            system_prompt = "你是一位专业的建筑署SRR案件回复草拟助手。你可以参考包含多个真实案例的模板库。"
        
        user_prompt = f"""Template Examples Library (Type: {reply_type}):
        ---
        {template_content}
        ---

        Current Case Information (USE THESE DETAILS):
        {case_info}

        Conversation History:
        {history_text}

        User Provided Supplementary Information:
        {user_message}

        Task: Generate a professional {reply_type} reply draft. Output language: **{"Chinese only" if language == 'zh' else "English only"}** (based on the user's supplementary information language).

        Instructions:
        1. Analyze the subject matter and select the most appropriate example from the template library
        2. Adapt the selected example to match the current case specifics
        3. **IMPORTANT**: Use the case information provided above to fill in details:
        - Use the actual Case Number, Slope Number, Location from the case data
        - Use the Nature of Request and Subject Matter to determine the appropriate scenario
        - If dates are not provided by user, you can use placeholder dates like "近期" (recently) or "将于[时间]内" (within [timeframe])
        4. Maintain the formal and professional tone of the examples
        5. **Bilingual output (if required by template):** If the template is bilingual, output Chinese and English in TWO SEPARATE BLOCKS with clear headings. Do NOT interleave (e.g. one line Chinese, one line English). Use this format:
        - First block: "【中文版本】" or "中文版本:" then the full Chinese draft
        - Second block: "【English Version】" or "English Version:" then the full English draft
        6. When output is single-language (as above), produce only that language. When both are needed, use the two-block format above.
        7. Only use information from the case data and user's supplementary information
        8. Do not fabricate specific dates, names, or technical details not provided

        Output: The complete, ready-to-use reply draft with case details filled in."""
        
        self.logger.info(f"🔄 Generating {reply_type} reply draft in {language}...")
        
        # 调用OpenAI API
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            max_tokens=3000,
            temperature=0.4
        )
        
        # 提取回复内容
        if response and response.choices and len(response.choices) > 0:
            draft_reply = response.choices[0].message.content
            if draft_reply and draft_reply.strip():
                self.logger.info(f"✅ Draft reply generated successfully ({len(draft_reply)} characters)")
                return {
                    "is_question": False,
                    "message": draft_reply,
                    "draft_reply": draft_reply.strip(),
                    "reply_slip_selections": self._build_reply_slip_selections(reply_type, case_data),
                    "deadline": self._resolve_reply_deadline(reply_type, case_data),
                }
        
        self.logger.warning("⚠️ Draft reply generation returned empty response")
        return None

    def generate_reply_draft_stream(
        self,
        reply_type: str,
        case_data: dict,
        template_content: str,
        conversation_history: list,
        user_message: str,
        language: str
    ):
        """Stream reply draft chunks. Yields non-empty string chunks."""
        try:
            if not self.api_key or not self.client:
                self.logger.warning("⚠️ API key not set or client not initialized")
                return
            history_text = ""
            if conversation_history:
                for msg in conversation_history:
                    role = msg.get('role', '')
                    content = msg.get('content', '')
                    history_text += f"{role}: {content}\n\n"
            if not user_message or user_message.strip().lower() in ['无', 'none', 'skip', '']:
                user_message = "请直接使用案件数据生成回复，无额外补充。" if language == 'zh' else "Please generate reply using case data directly, no additional information."
            case_info = f"""
            - Case Number: {case_data.get('C_case_number', 'N/A')}
            - Date Received: {case_data.get('A_date_received', 'N/A')}
            - Source: {case_data.get('B_source', 'N/A')}
            - Type: {case_data.get('D_type', 'N/A')}
            - Slope Number: {case_data.get('G_slope_no', 'N/A')}
            - Location: {case_data.get('H_location', 'N/A')}
            - Subject Matter: {case_data.get('J_subject_matter', 'N/A')}
            - Nature of Request: {case_data.get('I_nature_of_request', 'N/A')}
            - Caller: {case_data.get('E_caller_name', 'N/A')}
            - Contact: {case_data.get('F_contact_no', 'N/A')}
            - 10-day Due: {case_data.get('K_10day_rule_due_date', 'N/A')}
            - ICC Interim Due: {case_data.get('L_icc_interim_due', 'N/A')}
            - ICC Final Due: {case_data.get('M_icc_final_due', 'N/A')}"""
            system_prompt = "You are an expert assistant for drafting official ArchSD SRR case replies. You have access to a template library containing multiple real-world examples."
            if language == 'zh':
                system_prompt = "你是一位专业的建筑署SRR案件回复草拟助手。你可以参考包含多个真实案例的模板库。"
            user_prompt = f"""Template Examples Library (Type: {reply_type}):
            ---
            {template_content}
            ---

            Current Case Information (USE THESE DETAILS):
            {case_info}

            Conversation History:
            {history_text}

            User Provided Supplementary Information:
            {user_message}

            Task: Generate a professional {reply_type} reply draft. Output language: **{"Chinese only" if language == 'zh' else "English only"}**.

            Instructions:
            1. Analyze the subject matter and select the most appropriate example from the template library
            2. Adapt the selected example to match the current case specifics
            3. Use the case information provided above to fill in details
            4. Maintain the formal and professional tone of the examples
            5. Only use information from the case data and user's supplementary information
            6. Do not fabricate specific dates, names, or technical details not provided

            Output: The complete, ready-to-use reply draft with case details filled in."""
            self.logger.info(f"🔄 Streaming {reply_type} reply draft in {language}...")
            stream = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=3000,
                temperature=0.4,
                stream=True
            )
            for chunk in stream:
                if chunk and chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta and getattr(delta, "content", None):
                        yield delta.content
        except Exception as e:
            self.logger.error(f"❌ Reply draft stream failed: {type(e).__name__} - {e}")
            import traceback
            self.logger
            yield ""

    # 二次审核AI Summary
    def _review_sum_(self, input_str: str, correction_dict: Dict[str, Any]) -> str:
        """
        Use LLM API to correct keywords in the input string using the provided dictionary
        
        Args:
            input_str: Input string that may contain keywords needing correction
            correction_dict: Dictionary containing correct keyword mappings
            
        Returns:
            Corrected string with keywords replaced based on the dictionary, or None on failure
        """
        try:
            # Check API key and client
            if not self.api_key or not self.client:
                self.logger.warning("⚠️ API key not set or client not initialized, cannot use OpenAI API")
                return None
            
            # Validate input
            if not isinstance(input_str, str):
                self.logger.error(f"❌ Invalid input_str type: {type(input_str)}, expected str")
                return None
            
            if not input_str.strip():
                self.logger.warning("⚠️ Empty input_str provided")
                return input_str
            
            if not isinstance(correction_dict, dict):
                self.logger.error(f"❌ Invalid correction_dict type: {type(correction_dict)}, expected dict")
                return input_str
            
            # Convert dict to readable format
            dict_content = ""
            for key, value in correction_dict.items():
                dict_content += f"- {key}: {value}\n"
            
            # Build prompt for keyword correction
            prompt = f"""Correct keywords in the following input string based on the provided dictionary.
First, read this text and understand the content it describes:
INPUT STRING: {input_str}

Next, read the dictionary. I will explain the meaning of each key-value pair in it:
CORRECTION DICTIONARY: {dict_content}
- A_date_received: Date of Referral
- B_source: ICC, TMO, RCC (TMO for ASD PDF, RCC for RCC PDF)
- C_case_number: 1823 Case Number
- D_type: Emergency/Urgent/General
- E_caller_name: Caller/Inspection Officer name
- F_contact_no: Contact Number
- G_slope_no: Slope Number (e.g., 11SW-D/CR995, NOT with date suffix)
- H_location: Location/District
- I_nature_of_request: 2-20 word action phrase "[action] at [slope/treeID]"
- J_subject_matter: Category from rules below
- K_10day_rule_due_date: 10-day Rule Due Date
- L_icc_interim_due: ICC Interim Reply Due Date
- M_icc_final_due: ICC Final Reply Due Date
- N_works_completion_due: Works Completion Due Date
- O1_fax_to_contractor: Fax to Contractor Date
- O2_email_send_time: Email Send Time
- P_fax_pages: Fax Pages count
- Q_case_details: Case Details/Follow-up Actions

INSTRUCTIONS:
1. Focus on checking whether the personal names and place names appearing in the string (str) are inconsistent with those recorded in the dictionary. 
If there is any inconsistency, the dictionary shall prevail, and the addresses appearing in the string shall be revised accordingly.
2. Maintain the original structure and meaning of the string
3. Only change keywords that appear in the dictionary
4. Return the corrected string in the same language as the input

OUTPUT: 
Return only the corrected string, no explanations."""

            self.logger.info("🔄 Calling OpenAI API for keyword correction...")
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a keyword correction assistant. You help correct keywords in text using provided dictionary mappings."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2000,
                temperature=0.1  # Low temperature for accurate corrections
            )
            
            # Extract response content
            if response and response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                if content and content.strip():
                    corrected_str = content.strip()
                    self.logger.info(f"✅ Keyword correction completed successfully")
                    return corrected_str
            
            self.logger.warning("⚠️ OpenAI API response is empty or invalid")
            return input_str
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            self.logger.error(f"❌ Keyword correction failed: {error_type} - {error_msg}")
            import traceback
            self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return input_str

# Global LLM service instance
_llm_service = None

def init_llm_service(api_key: str, provider: str = "openai", proxy_url: str = None, use_proxy: bool = False):
    """
    Initialize global LLM service instance
    
    Args:
        api_key: API key
        provider: API provider, "openai" (default: "openai")
        proxy_url: Proxy URL (e.g., "http://127.0.0.1:7890")
        use_proxy: Whether to use proxy (default: False)
    """
    global _llm_service
    _llm_service = LLMService(api_key, provider, proxy_url, use_proxy)

def get_llm_service() -> LLMService:
    """
    Get global LLM service instance
    
    Returns:
        LLMService instance
    """
    global _llm_service
    if _llm_service is None:
        raise RuntimeError("LLM service not initialized, please call init_llm_service() first")
    return _llm_service
