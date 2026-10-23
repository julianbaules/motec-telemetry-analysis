function results = balance_analysis(laps, corners, outDir)
%BALANCE_ANALYSIS Steady-state handling balance from tyre slip angles.
%
%   Linear bicycle model: in a steady corner the road-wheel steer angle is
%       delta = L/R + (alpha_f - alpha_r)
%   so the difference between front and rear slip angles is the part of the
%   steering that is NOT explained by geometry:
%       balance = |alpha_f| - |alpha_r|   > 0 understeer, < 0 oversteer
%   Its slope against lateral acceleration is the understeer gradient K
%   (deg/g).
%
%   The analysis keeps quasi-steady cornering samples only (no brake,
%   lateral g almost constant), fits K per speed band and gives the mean
%   balance in each corner. It also estimates the steering ratio from the
%   front toe signal, which in this export follows the steering.

    fs = 20;                                   % Hz
    clean = laps(strcmp({laps.status}, 'clean'));

    % ---------------------------------------------------- 1. stack clean laps
    ay = []; bal = []; v = []; dist = []; brake = []; steer = []; toe = [];
    for k = 1:numel(clean)
        T = clean(k).data;
        aF = (T.("Tire Slip Angle FL") + T.("Tire Slip Angle FR")) / 2;
        aR = (T.("Tire Slip Angle RL") + T.("Tire Slip Angle RR")) / 2;
        ay    = [ay;    T.("CG Accel Lateral")];                    %#ok<AGROW>
        bal   = [bal;   abs(aF) - abs(aR)];                         %#ok<AGROW>
        v     = [v;     T.("Ground Speed")];                        %#ok<AGROW>
        dist  = [dist;  T.Distance];                                %#ok<AGROW>
        brake = [brake; T.("Brake Pos")];                           %#ok<AGROW>
        steer = [steer; T.("Steering Angle")];                      %#ok<AGROW>
        toe   = [toe;   (T.("Toe In FL") - T.("Toe In FR")) / 2];   %#ok<AGROW>
    end

    % ---------------------------------------------------- 2. quasi-steady samples
    % gradient() is computed over the stacked laps; the few samples at the
    % joins between two laps are removed by the other conditions.
    jerk = abs(gradient(ay)) * fs;                                  % g/s
    qs = abs(ay) > 0.3 & brake < 2 & v > 60 & jerk < 1.0;

    % ---------------------------------------------------- 3. understeer gradient
    bands = [60 110; 110 150; 150 250];
    bandNames = ["60-110 km/h", "110-150 km/h", "> 150 km/h"];
    colors = [0.165 0.471 0.839; 0.106 0.686 0.478; 0.922 0.408 0.204];
    K = zeros(3, 1); b = zeros(3, 1); n = zeros(3, 1);

    fig = figure('Color', 'w', 'Position', [100 100 1100 420]);
    tl = tiledlayout(fig, 1, 2, 'TileSpacing', 'compact');
    title(tl, 'Handling balance from tyre slip angles (clean laps)', 'FontWeight', 'bold');

    ax1 = nexttile(tl); hold(ax1, 'on'); grid(ax1, 'on');
    for i = 1:3
        m = qs & v >= bands(i, 1) & v < bands(i, 2);
        p = polyfit(abs(ay(m)), bal(m), 1);
        K(i) = p(1); b(i) = p(2); n(i) = nnz(m);
        scatter(ax1, abs(ay(m)), bal(m), 6, colors(i, :), 'filled', ...
                'MarkerFaceAlpha', 0.25, 'HandleVisibility', 'off');
        x = linspace(0.3, max(abs(ay(m))), 20);
        plot(ax1, x, polyval(p, x), 'Color', colors(i, :), 'LineWidth', 2, ...
             'DisplayName', sprintf('%s: K = %.2f deg/g', bandNames(i), K(i)));
    end
    yline(ax1, 0, 'k-', 'HandleVisibility', 'off');
    xlabel(ax1, '|Lateral acceleration| (g)');
    ylabel(ax1, '|\alpha_f| - |\alpha_r| (deg)   > 0 = understeer');
    legend(ax1, 'Location', 'northwest', 'Box', 'off');
    ylim(ax1, [-4 5]);

    % ---------------------------------------------------- 4. balance per corner
    nC = height(corners);
    cornerBal = zeros(nC, 1);
    for c = 1:nC
        m = dist >= corners.Start_m(c) & dist <= corners.End_m(c) & abs(ay) > 1.0 & brake < 2;
        cornerBal(c) = mean(bal(m));
    end
    ax2 = nexttile(tl);
    bar(ax2, 1:nC, cornerBal, 0.6, 'FaceColor', [0.165 0.471 0.839], 'EdgeColor', 'none');
    xticks(ax2, 1:nC);
    xticklabels(ax2, corners.Corner);
    grid(ax2, 'on');
    ylabel(ax2, 'Mean balance mid-corner (deg)');
    title(ax2, 'Mid-corner balance (|a_y| > 1 g, no brake)', 'FontWeight', 'normal');
    for c = 1:nC
        text(ax2, c, cornerBal(c) + 0.04, sprintf('%.2f\n%.0f km/h', cornerBal(c), corners.ApexSpeed_kmh(c)), ...
             'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom', 'FontSize', 8);
    end
    ylim(ax2, [min(0, min(cornerBal) * 1.5), max(cornerBal) * 1.5]);
    exportgraphics(fig, fullfile(outDir, 'matlab_01_balance.png'), 'Resolution', 160);

    % ---------------------------------------------------- 5. steering ratio
    m = abs(steer) < 120;
    pr = polyfit(toe(m), steer(m), 1);
    r = corrcoef(toe(m), steer(m));
    fig2 = figure('Color', 'w', 'Position', [100 100 520 420]);
    scatter(toe(m), steer(m), 4, [0.32 0.32 0.31], 'filled', 'MarkerFaceAlpha', 0.2);
    hold on; grid on;
    x = linspace(min(toe(m)), max(toe(m)), 10);
    plot(x, polyval(pr, x), 'Color', [0.165 0.471 0.839], 'LineWidth', 2);
    xlabel('Front road-wheel angle from toe signal (deg)');
    ylabel('Steering wheel angle (deg)');
    title(sprintf('Steering ratio estimate: %.1f : 1  (R^2 = %.4f)', pr(1), r(1, 2)^2));
    exportgraphics(fig2, fullfile(outDir, 'matlab_02_steering_ratio.png'), 'Resolution', 160);

    % ---------------------------------------------------- 6. results
    results.speedBands = bandNames';
    results.K_deg_per_g = K;
    results.intercept_deg = b;
    results.nSamples = n;
    results.balanceAt1p5g_deg = K * 1.5 + b;
    results.cornerBalance = table(corners.Corner, corners.Direction, corners.ApexSpeed_kmh, cornerBal, ...
        'VariableNames', {'Corner', 'Direction', 'ApexSpeed_kmh', 'MeanBalance_deg'});
    results.steeringRatio = pr(1);
    results.steeringRatioR2 = r(1, 2)^2;
end
