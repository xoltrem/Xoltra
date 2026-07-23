# Vercel deployment setup

To avoid the "not a contributor" error from the GitHub/Vercel integration, deploy through GitHub Actions using a Vercel token.

## Required GitHub repository secrets

Add these in GitHub repository settings -> Secrets and variables -> Actions:

- VERCEL_TOKEN
- VERCEL_ORG_ID
- VERCEL_PROJECT_ID

## How to get them

1. Install the Vercel CLI locally and log in:
   - npm i -g vercel
   - vercel login
2. Link your project:
   - vercel link
3. Copy the values from the generated .vercel/project.json or Vercel dashboard.

The workflow at .github/workflows/vercel-deploy.yml will deploy automatically on pushes to main.
