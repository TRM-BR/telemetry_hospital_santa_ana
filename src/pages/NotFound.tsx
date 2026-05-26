import { useNavigate } from 'react-router-dom';

const NotFound = () => {
  const navigate = useNavigate();
  return (
    <main className="min-h-screen flex items-center justify-center bg-secondary p-8">
      <div className="text-center">
        <p className="text-[10px] uppercase tracking-[0.3em] text-muted-foreground">Erro 404</p>
        <h1 className="mt-2 text-5xl font-bold text-foreground">Página não encontrada</h1>
        <p className="mt-4 text-sm text-muted-foreground max-w-md">
          O endereço que você acessou não existe ou foi removido.
        </p>
        <button
          type="button"
          onClick={() => navigate('/menu')}
          className="mt-8 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-soft hover:bg-primary-glow transition-smooth"
        >
          Voltar ao menu
        </button>
      </div>
    </main>
  );
};

export default NotFound;
