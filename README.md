# Strainforge

Cold forming load and energy calculator for tool design. Covers ten processes: cut off, closed upset, open upset, setting to perform, pre-upsetting form, reduction, trap extrusion, backward extrusion, piercing and trimming.

For each step it gives the press load F (kN), forming energy W (kJ), deformation grade φ and the tooling checks (buckling ratio, head cracking, area change, minimum bottom depth). It also shows every intermediate value, the equations used and a ±30 % load sensitivity chart.

Flow stress follows the Ludwik curve kf = C·φⁿ with material constants from the built-in library of 34 materials.

## Run

It is one static file. Open `index.html` in a browser, or deploy the folder as a static site (Vercel: framework preset "Other", no build command).
