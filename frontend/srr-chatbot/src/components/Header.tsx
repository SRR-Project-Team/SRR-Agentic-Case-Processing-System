import React from 'react';
import { Bot, MessageCircle } from 'lucide-react';

interface HeaderProps {
  title?: string;
  onMenuToggle?: () => void;
  sidebarCollapsed?: boolean;
}

const Header: React.FC<HeaderProps> = ({
  title = 'SRR Chatbot',
  onMenuToggle,
}) => {
  return (
    <header className="h-16 flex-shrink-0 border-b border-border shadow-sm sticky top-0 z-10 header-bar bg-background">
      <div className="h-full flex items-center justify-between">
        <div className="flex items-center gap-3 pl-0">
          {onMenuToggle && (
            <button
              type="button"
              onClick={onMenuToggle}
              className="flex items-center justify-center w-12 h-12 rounded-full gradient-red-yellow hover:opacity-90 hover:shadow-md transition-all duration-200 flex-shrink-0"
              aria-label="Expand/collapse sidebar"
              title="Expand/collapse sidebar"
            >
              <Bot size={25} className="text-white" />
            </button>
          )}
          <div className="flex items-center gap-2">
            <div className="w-12 h-12 rounded-full gradient-red-yellow flex items-center justify-center flex-shrink-0">
              <MessageCircle size={30} className="text-white" />
            </div>
            <h1 className="text-xl font-semibold text-foreground">{title}</h1>
          </div>
        </div>
        <div className="pr-4" />
      </div>
    </header>
  );
};

export default Header;