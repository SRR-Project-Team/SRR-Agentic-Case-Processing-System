import React, { useState, FormEvent } from 'react';
import confetti from 'canvas-confetti';
import { useAuth } from '../contexts/AuthContext';
import { Lock, Phone, AlertCircle, Loader2 } from 'lucide-react';
import GradientButton from './GradientButton';

interface LoginPageProps {
  onSwitchToRegister: () => void;
  /** When true, render only the form card (for use inside modal) */
  embedded?: boolean;
}

/**
 * Login Page Component
 * 
 * Provides user authentication interface with:
 * - Phone number and password input
 * - Form validation
 * - Error handling
 * - Loading states
 */
const LoginPage: React.FC<LoginPageProps> = ({ onSwitchToRegister, embedded = false }) => {
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!phone.trim()) {
      setError('Please enter phone number');
      return;
    }
    if (!password) {
      setError('Please enter password');
      return;
    }
    setLoading(true);
    try {
      await login(phone.trim(), password);
      console.log('✅ 登录成功');
      const end = Date.now() + 1800;
      const burst = () => {
        confetti({ particleCount: 6, angle: 60, spread: 65, origin: { x: 0 }, colors: ['#ef4444', '#f97316', '#eab308'] });
        confetti({ particleCount: 6, angle: 120, spread: 65, origin: { x: 1 }, colors: ['#ef4444', '#f97316', '#eab308'] });
        if (Date.now() < end) requestAnimationFrame(burst);
      };
      burst();
    } catch (err: any) {
      console.error('❌ 登录失败:', err);
      setError(err.message || 'Login failed. Please check phone number and password.');
    } finally {
      setLoading(false);
    }
  };

  const content = (
    <div className={`login-container bg-white rounded-2xl shadow-xl border border-gray-100 p-8 max-w-md w-full animate-fade-in ${embedded ? 'login-container-embedded' : ''}`}>
        <div className="login-header text-center mb-8">
          <div className="login-logo mb-4">
            <div className="w-12 h-12 rounded-full gradient-red-yellow flex items-center justify-center mx-auto">
              <Lock size={22} className="text-white" />
            </div>
          </div>
          <h1 className="login-title text-2xl font-bold text-gray-800 mb-2">SRR Case Processing System</h1>
          <p className="login-subtitle text-gray-600">Please sign in to continue</p>
        </div>

        <form className="login-form" onSubmit={handleLogin}>
          {error && (
            <div className="login-error bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-start gap-3 animate-slide-in">
              <AlertCircle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
              <span className="error-message text-red-600 text-sm">{error}</span>
            </div>
          )}

          <div className="form-group mb-6 animate-fade-in" style={{ animationDelay: '0.1s' }}>
            <label htmlFor="phone" className="form-label block text-sm font-medium text-gray-700 mb-2">
              Phone number
            </label>
            <div className="relative">
              <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
                <Phone size={16} />
              </div>
              <input
                id="phone"
                type="tel"
                className="form-input w-full px-10 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent transition-all"
                placeholder="8-digit Hong Kong phone number"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={loading}
                autoComplete="tel"
                maxLength={8}
              />
            </div>
          </div>

          <div className="form-group mb-8 animate-fade-in" style={{ animationDelay: '0.2s' }}>
            <label htmlFor="password" className="form-label block text-sm font-medium text-gray-700 mb-2">
              Password
            </label>
            <div className="relative">
              <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
                <Lock size={16} />
              </div>
              <input
                id="password"
                type="password"
                className="form-input w-full px-10 py-3 rounded-lg border border-gray-300 focus:outline-none focus:ring-2 focus:ring-red-400 focus:border-transparent transition-all"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                autoComplete="current-password"
              />
            </div>
          </div>

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
                <span>Signing in...</span>
              </>
            ) : (
              'Sign in'
            )}
          </GradientButton>
        </form>

        <div className="login-footer text-center animate-fade-in" style={{ animationDelay: '0.4s' }}>
          <p className="footer-text text-gray-600 text-sm">
            Don't have an account?
            <button 
              className="link-button ml-1 text-red-500 hover:text-red-700 font-medium transition-colors"
              onClick={onSwitchToRegister}
              disabled={loading}
            >
              Register now
            </button>
          </p>
        </div>
      </div>
  );

  if (embedded) return content;
  return (
    <div className="login-page min-h-screen bg-gradient-to-br from-white to-red-50 flex items-center justify-center p-4">
      {content}
    </div>
  );
};

export default LoginPage;
