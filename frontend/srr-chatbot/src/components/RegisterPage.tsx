import React, { useState, FormEvent } from 'react';
import { register } from '../services/api';
import { Lock, User, Building, Mail, Phone, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import GradientButton from './GradientButton';

interface RegisterPageProps {
  onSwitchToLogin: () => void;
  /** When true, render only the form card (for use inside modal) */
  embedded?: boolean;
}

/**
 * Register Page Component
 * 
 * Provides user registration interface with:
 * - Phone number, password, and confirm password input
 * - Full name, department, and email input
 * - Form validation
 * - Error handling
 * - Loading states
 */
const RegisterPage: React.FC<RegisterPageProps> = ({ onSwitchToLogin, embedded = false }) => {
  const [formData, setFormData] = useState({
    phone: '',
    password: '',
    confirmPassword: '',
    fullName: '',
    department: '',
    email: ''
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value
    });
  };

  const validateForm = (): string | null => {
    if (!formData.phone.trim()) {
      return 'Please enter phone number';
    }
    const phoneRegex = /^[2-9]\d{7}$/;
    if (!phoneRegex.test(formData.phone.replace(/\s/g, ''))) {
      return 'Please enter a valid Hong Kong phone number (8 digits)';
    }
    if (!formData.password) {
      return 'Please enter password';
    }
    if (formData.password.length < 6) {
      return 'Password must be at least 6 characters';
    }
    if (new TextEncoder().encode(formData.password).length > 72) {
      return 'Password must be at most 72 bytes (about 72 ASCII or 24 Chinese characters)';
    }
    if (formData.password !== formData.confirmPassword) {
      return 'Passwords do not match';
    }
    if (!formData.fullName.trim()) {
      return 'Please enter your name';
    }
    if (formData.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      return 'Please enter a valid email address';
    }
    
    return null;
  };

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    
    // Clear previous errors and success
    setError(null);
    setSuccess(false);
    
    // Validate form
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }
    
    setLoading(true);
    
    try {
      await register({
        phone_number: formData.phone.trim(),
        password: formData.password,
        full_name: formData.fullName.trim(),
        department: formData.department.trim() || undefined,
        email: formData.email.trim() || undefined,
        role: 'user'
      });
      
      setSuccess(true);
      console.log('✅ 注册成功');
      
      // Auto switch to login page after 2 seconds
      setTimeout(() => {
        onSwitchToLogin();
      }, 2000);
      
    } catch (err: any) {
      console.error('❌ 注册失败:', err);
      setError(err.message || 'Registration failed. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const content = (
    <div className={`register-container bg-white rounded-2xl shadow-xl border border-gray-100 p-8 max-w-md w-full animate-fade-in max-h-[90vh] overflow-y-auto ${embedded ? 'register-container-embedded' : ''}`}>
        <div className="register-header text-center mb-8">
          <div className="register-logo mb-4">
            <div className="w-12 h-12 rounded-full gradient-red-yellow flex items-center justify-center mx-auto">
              <User size={22} className="text-white" />
            </div>
          </div>
          <h1 className="register-title text-2xl font-bold text-gray-800 mb-2">Create account</h1>
          <p className="register-subtitle text-gray-600">Fill in the form below to register</p>
        </div>

        {success ? (
          <div className="success-message text-center py-8 animate-fade-in">
            <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
              <CheckCircle size={24} className="text-green-500" />
            </div>
            <h2 className="text-xl font-bold text-gray-800 mb-2">Registration successful!</h2>
            <p className="text-gray-600">Redirecting to login...</p>
          </div>
        ) : (
          <form className="register-form" onSubmit={handleRegister}>
            <div className="form-section mb-8 animate-fade-in" style={{ animationDelay: '0.1s' }}>
              <h3 className="section-title text-lg font-semibold text-gray-700 mb-4">Account info</h3>
              
              <div className="form-group mb-4">
                <label htmlFor="phone" className="form-label block text-sm font-medium text-gray-700 mb-2">
                  Phone number <span className="required text-red-500">*</span>
                </label>
                <div className="relative">
                  <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
                    <Phone size={16} />
                  </div>
                  <input
                    id="phone"
                    name="phone"
                    type="tel"
                    className="form-input w-full px-10 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent transition-all"
                    placeholder="8-digit HK phone (e.g. 91234567)"
                    value={formData.phone}
                    onChange={handleChange}
                    disabled={loading}
                    autoComplete="tel"
                    maxLength={8}
                  />
                </div>
              </div>

              <div className="form-group mb-4">
                <label htmlFor="password" className="form-label block text-sm font-medium text-gray-700 mb-2">
                  Password <span className="required text-red-500">*</span>
                </label>
                <div className="relative">
                  <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
                    <Lock size={16} />
                  </div>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    className="form-input w-full px-10 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent transition-all"
                    placeholder="At least 6 characters"
                    value={formData.password}
                    onChange={handleChange}
                    disabled={loading}
                    autoComplete="new-password"
                  />
                </div>
              </div>

              <div className="form-group mb-4">
                <label htmlFor="confirmPassword" className="form-label block text-sm font-medium text-gray-700 mb-2">
                  Confirm password <span className="required text-red-500">*</span>
                </label>
                <div className="relative">
                  <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
                    <Lock size={16} />
                  </div>
                  <input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    className="form-input w-full px-10 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent transition-all"
                    placeholder="Enter password again"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    disabled={loading}
                    autoComplete="new-password"
                  />
                </div>
              </div>
            </div>

            <div className="form-section mb-8 animate-fade-in" style={{ animationDelay: '0.2s' }}>
              <h3 className="section-title text-lg font-semibold text-gray-700 mb-4">Personal info</h3>
              
              <div className="form-group mb-4">
                <label htmlFor="fullName" className="form-label block text-sm font-medium text-gray-700 mb-2">
                  Full name <span className="required text-red-500">*</span>
                </label>
                <div className="relative">
                  <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
                    <User size={16} />
                  </div>
                  <input
                    id="fullName"
                    name="fullName"
                    type="text"
                    className="form-input w-full px-10 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent transition-all"
                    placeholder="Your name"
                    value={formData.fullName}
                    onChange={handleChange}
                    disabled={loading}
                    autoComplete="name"
                  />
                </div>
              </div>

              <div className="form-group mb-4">
                <label htmlFor="department" className="form-label block text-sm font-medium text-gray-700 mb-2">
                  Department
                </label>
                <div className="relative">
                  <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
                    <Building size={16} />
                  </div>
                  <input
                    id="department"
                    name="department"
                    type="text"
                    className="form-input w-full px-10 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent transition-all"
                    placeholder="Your department (optional)"
                    value={formData.department}
                    onChange={handleChange}
                    disabled={loading}
                    autoComplete="organization"
                  />
                </div>
              </div>

              <div className="form-group mb-4">
                <label htmlFor="email" className="form-label block text-sm font-medium text-gray-700 mb-2">
                  Email
                </label>
                <div className="relative">
                  <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
                    <Mail size={16} />
                  </div>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    className="form-input w-full px-10 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent transition-all"
                    placeholder="Your email (optional)"
                    value={formData.email}
                    onChange={handleChange}
                    disabled={loading}
                    autoComplete="email"
                  />
                </div>
              </div>
            </div>

            {error && (
              <div className="register-error bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-start gap-3 animate-slide-in">
                <AlertCircle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
                <span className="error-message text-red-600 text-sm">{error}</span>
              </div>
            )}

            <GradientButton
              disabled={loading}
              fullWidth
              size="lg"
              className="mb-6 animate-fade-in"
              style={{ animationDelay: '0.3s' }}
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin mr-2" />
                  <span>Registering...</span>
                </>
              ) : (
                'Register'
              )}
            </GradientButton>
          </form>
        )}

        <div className="register-footer text-center animate-fade-in" style={{ animationDelay: '0.4s' }}>
          <p className="footer-text text-gray-600 text-sm">
            Already have an account?
            <button 
              className="link-button ml-1 text-red-500 hover:text-red-700 font-medium transition-colors"
              onClick={onSwitchToLogin}
              disabled={loading}
            >
              Sign in
            </button>
          </p>
        </div>
      </div>
  );

  if (embedded) return content;
  return (
    <div className="register-page min-h-screen bg-gradient-to-br from-white to-red-50 flex items-center justify-center p-4">
      {content}
    </div>
  );
};

export default RegisterPage;
