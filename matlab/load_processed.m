function laps = load_processed(processedDir)
%LOAD_PROCESSED Load the published per-lap CSV files.
%   laps = LOAD_PROCESSED(processedDir) returns a struct array with one
%   element per lap:
%       laps(k).stint   'Stint 1', 'Stint 6', ...
%       laps(k).lap     lap number (0 = out-lap)
%       laps(k).status  'out-lap' | 'clean' | 'incident' | 'incomplete'
%       laps(k).data    table with every exported channel
%
%   Channel names contain spaces ("Ground Speed"), so the tables keep the
%   original names and columns are read with T.("Ground Speed").
%   Requires MATLAB R2020b or newer (readtable 'VariableNamingRule').

    summary = readtable(fullfile(processedDir, 'laps.csv'), 'TextType', 'string');
    files = dir(fullfile(processedDir, 'stint*_lap*.csv'));

    laps = struct('stint', {}, 'lap', {}, 'status', {}, 'data', {});
    for k = 1:numel(files)
        T = readtable(fullfile(files(k).folder, files(k).name), ...
                      'VariableNamingRule', 'preserve', 'TextType', 'string');
        stint = T.Stint(1);
        lap = T.Lap(1);
        row = summary.Stint == stint & summary.Lap == lap;

        laps(end + 1).stint = char(stint);                         %#ok<AGROW>
        laps(end).lap = lap;
        laps(end).status = char(summary.Status(row));
        laps(end).data = T;
    end
end
