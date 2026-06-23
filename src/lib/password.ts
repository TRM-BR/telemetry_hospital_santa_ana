const SPECIAL = '!@#$%^&*()_+-=[]{}|;:\'",.<>?/`~\\';

export interface PasswordValidationResult {
  valid: boolean;
  errors: string[];
}

export function validatePassword(
  password: string,
  username?: string,
  email?: string,
): PasswordValidationResult {
  const errors: string[] = [];

  if (password.length < 10) {
    errors.push('Mínimo de 10 caracteres.');
  }
  if (!/[A-Z]/.test(password)) {
    errors.push('Pelo menos uma letra maiúscula.');
  }
  if (!/[a-z]/.test(password)) {
    errors.push('Pelo menos uma letra minúscula.');
  }
  if (!/[0-9]/.test(password)) {
    errors.push('Pelo menos um dígito.');
  }
  if (!SPECIAL.split('').some((c) => password.includes(c))) {
    errors.push('Pelo menos um caractere especial (!@#$%^&* etc.).');
  }
  if (username && username.length >= 3 && password.toLowerCase().includes(username.toLowerCase())) {
    errors.push('A senha não pode conter o nome de usuário.');
  }
  if (email) {
    const localPart = email.split('@')[0];
    if (localPart.length >= 3 && password.toLowerCase().includes(localPart.toLowerCase())) {
      errors.push('A senha não pode conter parte do email.');
    }
  }

  return { valid: errors.length === 0, errors };
}
