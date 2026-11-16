# Local ROMER stylesheet build

`theme.json` contains the exact Tailwind configuration extracted from the supplied `romer_command_dashboard/code.html`. Source HTML is parsed as data and is never executed during extraction. `original-source-sha256.json` records the four original HTML files without changing them.

The dashboard uses `src/app/static/fonts.css` and `src/app/static/tailwind.css` locally. The original Google Fonts CSS is retained here for provenance; all font URLs in the served stylesheet point to local WOFF2 files, including Vietnamese subsets. Font attribution, licenses, source URLs and binary hashes are under `src/app/static/assets/fonts/`.

After changing HTML or JavaScript, rebuild utilities with Node:

```powershell
node design_reference/build/build-css.cjs
```

The build scans all supplied templates and `src/app/static/*.{html,js}`. Tailwind CSS 3.4.17, forms 0.5.10, container queries 0.1.1 and Autoprefixer 10.4.21 are pinned in `package.json` and `package-lock.json`. During implementation these dependencies are isolated in the sibling workspace folder `romer-build`, with its npm cache also kept there. No global installation is required.

For an independent checkout, install in this build directory and run its build script:

```powershell
npm ci --prefix design_reference/build --ignore-scripts
npm run build --prefix design_reference/build
```

`ROMER_CSS_DEPENDENCIES` can instead point to a directory containing this pinned `package.json` and its installed `node_modules`.

The compiled CSS and vendored fonts are already present, so the application requires neither npm nor internet access to run.
