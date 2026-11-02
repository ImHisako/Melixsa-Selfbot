import ReactDOM from 'react-dom/client';
import './fonts.css';
import App from './App';
import { LanguageProvider } from './i18n';
import { AppIconProvider } from './hooks/useAppIcon';
import './styles.css';
import './viewport.css';

ReactDOM.createRoot(document.getElementById('root')!).render(<LanguageProvider><AppIconProvider><App /></AppIconProvider></LanguageProvider>);
