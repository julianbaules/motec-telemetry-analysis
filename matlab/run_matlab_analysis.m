%RUN_MATLAB_ANALYSIS Vehicle dynamics analysis, complementary to the Python pipeline.
%   Run from the matlab/ folder, after the Python pipeline (which produces
%   data/processed and reports/tables/corners.csv), or directly on the
%   published CSV files.
%
%   Outputs: reports/figures/matlab_*.png and reports/tables/matlab_*.csv
%   Tested target: MATLAB R2020b or newer, no toolbox required.

clear; close all; clc;

root = fileparts(fileparts(mfilename('fullpath')));
processedDir = fullfile(root, 'data', 'processed');
figDir = fullfile(root, 'reports', 'figures');
tableDir = fullfile(root, 'reports', 'tables');

laps = load_processed(processedDir);
corners = readtable(fullfile(tableDir, 'corners.csv'), 'TextType', 'string');
fprintf('%d laps loaded, %d clean\n', numel(laps), nnz(strcmp({laps.status}, 'clean')));

% 1. steady-state balance and steering ratio
bal = balance_analysis(laps, corners, figDir);
fprintf('\nUndersteer gradient per speed band\n');
disp(table(bal.speedBands, bal.K_deg_per_g, bal.intercept_deg, bal.balanceAt1p5g_deg, bal.nSamples, ...
     'VariableNames', {'Band', 'K_deg_per_g', 'Intercept_deg', 'BalanceAt1p5g_deg', 'Samples'}));
fprintf('Mid-corner balance\n');
disp(bal.cornerBalance);
fprintf('Steering ratio: %.1f:1 (R^2 = %.4f)\n', bal.steeringRatio, bal.steeringRatioR2);
writetable(bal.cornerBalance, fullfile(tableDir, 'matlab_corner_balance.csv'));

% 2. yaw stability at the T2 entry
stab = t2_stability_analysis(laps, figDir);
fprintf('\nT2 entry stability\n');
disp(stab);
writetable(stab, fullfile(tableDir, 'matlab_t2_stability.csv'));
