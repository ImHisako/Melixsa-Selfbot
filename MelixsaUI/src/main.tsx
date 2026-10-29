import ReactDOM from 'react-dom/client';
import './fonts.css';
import App from './App';
import { LanguageProvider } from './i18n';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(<LanguageProvider><App /></LanguageProvider>);
