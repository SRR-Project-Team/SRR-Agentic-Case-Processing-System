import React from 'react';

interface GradientButtonProps {
  children: React.ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'secondary' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  className?: string;
  fullWidth?: boolean;
  style?: React.CSSProperties;
}

const GradientButton: React.FC<GradientButtonProps> = ({
  children,
  onClick,
  variant = 'primary',
  size = 'md',
  disabled = false,
  className = '',
  fullWidth = false,
  style,
}) => {
  const baseClasses = 'rounded-lg font-medium transition-all duration-300 flex items-center justify-center';
  
  const sizeClasses = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg',
  };
  
  const variantClasses = {
    primary: 'gradient-red-yellow text-white hover:shadow-lg hover:shadow-red-200',
    secondary: 'gradient-yellow-red text-white hover:shadow-lg hover:shadow-yellow-200',
    outline: 'bg-white border-2 border-red-400 text-red-500 hover:bg-red-50',
  };
  
  const widthClass = fullWidth ? 'w-full' : '';
  
  const disabledClass = disabled ? 'opacity-50 cursor-not-allowed' : '';
  
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={style}
      className={`
        ${baseClasses}
        ${sizeClasses[size]}
        ${variantClasses[variant]}
        ${widthClass}
        ${disabledClass}
        ${className}
      `}
    >
      {children}
    </button>
  );
};

export default GradientButton;