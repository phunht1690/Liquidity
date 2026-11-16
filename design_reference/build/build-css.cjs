/* Build ROMER utilities locally. The supplied HTML is scanned as data only. */
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');

const project = path.resolve(__dirname, '../..');
const dependencyRoot = process.env.ROMER_CSS_DEPENDENCIES ||
  (fs.existsSync(path.join(__dirname, 'node_modules')) ? __dirname : path.resolve(project, '../romer-build'));
const localRequire = createRequire(path.join(dependencyRoot, 'package.json'));
const postcss = localRequire('postcss');
const tailwindcss = localRequire('tailwindcss');
const autoprefixer = localRequire('autoprefixer');
const theme = JSON.parse(fs.readFileSync(path.join(__dirname, 'theme.json'), 'utf8'));
const slash = value => value.replaceAll('\\', '/');
const config = {
  ...theme,
  content: [
    slash(path.join(project, 'design_reference/romer_*/code.html')),
    slash(path.join(project, 'src/app/static/*.{html,js}')),
  ],
  safelist: [
    'hidden', 'block', 'flex', 'grid', 'active',
    'text-secondary', 'text-error', 'text-primary', 'text-tertiary',
    'text-on-surface', 'text-on-surface-variant',
    'bg-secondary/10', 'bg-error/10', 'bg-primary/10',
    'border-secondary', 'border-error', 'border-primary',
  ],
  plugins: [localRequire('@tailwindcss/forms'), localRequire('@tailwindcss/container-queries')],
};
const input = fs.readFileSync(path.join(__dirname, 'input.css'), 'utf8');
const output = path.join(project, 'src/app/static/tailwind.css');
postcss([tailwindcss(config), autoprefixer]).process(input, { from: path.join(__dirname, 'input.css'), to: output })
  .then(result => {
    fs.writeFileSync(output, result.css, 'utf8');
    const manifest = { tailwindcss: localRequire('tailwindcss/package.json').version,
      plugins: { forms: localRequire('@tailwindcss/forms/package.json').version,
        containerQueries: localRequire('@tailwindcss/container-queries/package.json').version },
      themeSource: 'design_reference/romer_command_dashboard/code.html',
      content: ['design_reference/romer_*/code.html', 'src/app/static/*.{html,js}'],
      bytes: Buffer.byteLength(result.css),
    };
    fs.writeFileSync(path.join(__dirname, 'build-manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
    console.log(`Built ${manifest.bytes.toLocaleString()} bytes of local Tailwind CSS from exact ROMER source tokens.`);
  }).catch(error => { console.error(error.message); process.exitCode = 1; });
