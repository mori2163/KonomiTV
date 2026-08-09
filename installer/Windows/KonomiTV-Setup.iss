; KonomiTV の Windows インストーラー (Inno Setup 製)
; 従来の CLI インストーラー (KonomiTV-Installer.exe) に代わる、ウィザード形式のインストーラー
; 設定の入力を最小限に抑え、バックエンド (EDCB / Mirakurun) とエンコーダーは自動検出する
; インストール本体は同梱のインストールエンジン (KonomiTV-Installer-Engine.exe) が無人モードで実行する
;
; ビルド: iscc KonomiTV-Setup.iss (CI の build_installer.yaml で実行される)

#ifndef MyAppVersion
#define MyAppVersion "0.14.1"
#endif

#define MyAppName "KonomiTV"
#define MyAppPublisher "tsukumijima"
#define MyAppURL "https://github.com/tsukumijima/KonomiTV"
#define MyEngineFileName "KonomiTV-Installer-Engine.exe"

[Setup]
AppId={{8E9B1E6F-2A3B-4C7D-9F5A-6B4C3D2E1F0A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; インストール先のフォルダ (既存の CLI インストーラーの推奨値と同じ)
DefaultDirName=C:\KonomiTV
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 管理者権限での実行が必要 (Windows サービスの登録やファイアウォール設定のため)
PrivilegesRequired=admin
; Windows 10 / 11 (x64) のみに対応
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; 出力ファイル名 (KonomiTV-Setup-<バージョン>.exe)
OutputBaseFilename=KonomiTV-Setup-{#MyAppVersion}
OutputDir=..\dist
SetupIconFile=..\KonomiTV-Installer.ico
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 最初にようこそページを表示する (Inno Setup 6.3 以降はデフォルトで非表示のため、明示的に有効化する)
DisableWelcomePage=no
; ライセンス同意ページを表示する (MIT ライセンスの全文を表示し、同意しないと次へ進めない)
LicenseFile=..\..\License.txt
; アンインストール時にレジストリやファイルを残さないようにする
Uninstallable=yes
CreateUninstallRegKey=yes
; セットアップ中にブラウザで開く URL (完了ページのチェックボックスから実行)
[Run]
Filename: "https://my.local.konomi.tv:7000/"; Description: "KonomiTV をブラウザで開く"; Flags: postinstall nowait shellexec skipifsilent unchecked

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Icons]
; ブラウザで KonomiTV を開くショートカットをスタートメニューに作成する
Name: "{group}\KonomiTV"; Filename: "https://my.local.konomi.tv:7000/"

[Files]
; インストールエンジン (PyInstaller 製 exe) を一時フォルダに展開する
; dontcopy フラグにより、ウィザード中に ExtractTemporaryFile でいつでも展開できる
Source: "..\dist\{#MyEngineFileName}"; DestDir: "{tmp}"; Flags: ignoreversion dontcopy

[Code]
// ---------------------------------------------------------------------------
// ウィザードページと設定値のグローバル変数
// ---------------------------------------------------------------------------

var
  // バックエンド設定ページ
  BackendPage: TWizardPage;
  IPLabel: TNewStaticText;
  IPEdit: TNewEdit;
  DetectButton: TNewButton;
  EdcbRadio: TNewRadioButton;
  MirakurunRadio: TNewRadioButton;
  BackendResultLabel: TNewStaticText;

  // エンコーダー設定ページ
  EncoderPage: TWizardPage;
  EncoderDescriptionLabel: TNewStaticText;
  FfmpegRadio: TNewRadioButton;
  QsvenccRadio: TNewRadioButton;
  NvenccRadio: TNewRadioButton;
  VceenccRadio: TNewRadioButton;
  EncoderDetected: Boolean;
  GpuNames: String;   // 接続されている GPU 名 (複数ある場合はカンマ区切り)

  // サービスアカウント設定ページ
  ServicePage: TInputQueryWizardPage;

  // フォルダ設定ページ
  FolderPage: TWizardPage;
  RecordedFoldersLabel: TNewStaticText;
  RecordedFolderEdit: TNewEdit;
  RecordedFolderBrowseButton: TNewButton;
  RecordedFolderAddButton: TNewButton;
  RecordedFolderListBox: TNewListBox;
  RecordedFolderRemoveButton: TNewButton;
  CaptureFoldersLabel: TNewStaticText;
  CaptureFolderEdit: TNewEdit;
  CaptureFolderBrowseButton: TNewButton;
  CaptureFolderAddButton: TNewButton;
  CaptureFolderListBox: TNewListBox;
  CaptureFolderRemoveButton: TNewButton;

  // インストール進捗の表示 (標準のインストールページに配置する)
  ProgressMemo: TNewMemo;
  ProgressStatusLabel: TNewStaticText;

  // ウィザードで選択された設定値
  BackendType: String;   // 'EDCB' / 'Mirakurun' / '' (未検出)
  EdcbUrl: String;
  MirakurunUrl: String;
  EncoderType: String;   // 'FFmpeg' / 'QSVEncC' / 'NVEncC' / 'VCEEncC'
  RecordedFolders: String;   // 録画フォルダのリスト ('|' 区切り)
  CaptureFolders: String;    // キャプチャフォルダのリスト ('|' 区切り)

  // バックエンドの自動検出の状態
  BackendDetected: Boolean;      // 自動検出に成功したか
  Detecting: Boolean;            // 自動検出の実行中か
  DetectElapsedSeconds: Integer; // 自動検出の経過秒数
  DetectTimerID: UINT_PTR;       // 自動検出の経過秒数表示タイマーの ID
  DetectedIP: String;            // 自動検出に使用した IP アドレス

  // インストールの進捗表示用
  LastProgressLineCount: Integer;
  ProgressFilePath: String;      // 進捗ファイルのパス
  InstallFinished: Boolean;      // 進捗タイマーが完了 (DONE) / エラー (ERROR) を検出したか
  InstallErrorMessage: String;   // インストール失敗時のエラーメッセージ
  InstallProgressTimerID: UINT_PTR;  // 進捗ポーリングタイマーの ID

// ---------------------------------------------------------------------------
// 進捗表示のためのタイマー (user32.dll の SetTimer / KillTimer)
// ---------------------------------------------------------------------------

function SetTimer(hWnd: HWND; nIDEvent: UINT_PTR; uElapse: UINT; lpTimerFunc: NativeInt): UINT_PTR;
external 'SetTimer@user32.dll stdcall';
function KillTimer(hWnd: HWND; nIDEvent: UINT_PTR): BOOL;
external 'KillTimer@user32.dll stdcall';

// ---------------------------------------------------------------------------
// ヘルパー関数
// ---------------------------------------------------------------------------

// エンジン exe のパスを返す
function GetEnginePath: String;
begin
  Result := AddBackslash(ExpandConstant('{tmp}')) + '{#MyEngineFileName}';
end;

// 一時フォルダ内のファイルパスを返す
function GetTempFilePath(const FileName: String): String;
begin
  Result := AddBackslash(ExpandConstant('{tmp}')) + FileName;
end;

// 指定されたフォルダに KonomiTV がインストールされているか
function IsExistingKonomiTV(const Dir: String): Boolean;
begin
  Result := FileExists(AddBackslash(Dir) + 'config.yaml') and DirExists(AddBackslash(Dir) + 'server');
end;

// 指定されたフォルダが空かどうか
// (Inno Setup のアンインストーラー関連ファイル (unins000.*) のみが存在する場合は、
//  実質的に空のフォルダとして扱う。上書きインストール時にアンインストーラーが
//  「KonomiTV 以外のファイル」と誤検出されてインストールが止まるのを防ぐため)
function IsDirEmpty(const Dir: String): Boolean;
var
  FindRec: TFindRec;
begin
  Result := True;
  if FindFirst(AddBackslash(Dir) + '*', FindRec) then
  begin
    try
      repeat
        // アンインストーラー関連ファイルは「空」とみなして対象外にする
        // (エンジン側 (Installer.py) の inno_setup_uninstaller_files と同じ定義)
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') and
           (FindRec.Name <> 'unins000.exe') and (FindRec.Name <> 'unins000.dat') and
           (FindRec.Name <> 'unins000.msg') then
        begin
          Result := False;
          Exit;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

// 指定されたフォルダに KonomiTV 以外のファイルが存在するかどうか
// (アンインストール時にインストール先フォルダを削除する際、ユーザーデータなどの
//  KonomiTV 以外のファイルを誤って削除しないようにするためのチェック)
function HasForeignFiles(const Dir: String): Boolean;
var
  FindRec: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Dir) + '*', FindRec) then
  begin
    try
      repeat
        // KonomiTV がインストール時に作成する既知のファイル/フォルダのみを許可する
        // (config.yaml と server フォルダはエンジンが作成し、unins000.* は Inno Setup のアンインストーラー本体)
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') and
           (FindRec.Name <> 'config.yaml') and (FindRec.Name <> 'server') and
           (FindRec.Name <> 'unins000.exe') and (FindRec.Name <> 'unins000.dat') and
           (FindRec.Name <> 'unins000.msg') then
        begin
          Result := True;
          Exit;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

// エンジン exe を実行して終了コードを返す
function RunEngine(const Args: String; const Wait: Boolean): Integer;
var
  ResultCode: Integer;
begin
  if not FileExists(GetEnginePath) then
  begin
    MsgBox('インストールエンジンが見つかりませんでした。インストーラーが破損している可能性があります。', mbError, MB_OK);
    Result := -1;
    Exit;
  end;
  if Wait then
    Exec(GetEnginePath, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
  else
    Exec(GetEnginePath, Args, '', SW_HIDE, ewNoWait, ResultCode);
  Result := ResultCode;
end;

// バックエンドの自動検出を実行する
// 戻り値: 検出できた場合は True
function DetectBackendFromIP(const IP: String): Boolean;
var
  OutputFile: String;
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := False;
  BackendType := '';
  EdcbUrl := '';
  MirakurunUrl := '';
  OutputFile := GetTempFilePath('konomitv-backend-detect.txt');
  DeleteFile(OutputFile);

  // エンジンの --detect-backend モードで検出する
  if RunEngine('--detect-backend ' + IP + ' --output-file "' + OutputFile + '"', True) <> 0 then
  begin
    BackendResultLabel.Caption := 'バックエンドの検出に失敗しました。';
    Exit;
  end;

  // 検出結果 (key=value) を読み込む
  // (エンジンは UTF-8 で書き出すが、LoadStringsFromFile は BOM なし UTF-8 にも対応している)
  if LoadStringsFromFile(OutputFile, Lines) then
  begin
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      if Copy(Lines[I], 1, 8) = 'backend=' then
        BackendType := Copy(Lines[I], 9, Length(Lines[I]) - 8)
      else if Copy(Lines[I], 1, 9) = 'edcb_url=' then
        EdcbUrl := Copy(Lines[I], 10, Length(Lines[I]) - 9)
      else if Copy(Lines[I], 1, 14) = 'mirakurun_url=' then
        MirakurunUrl := Copy(Lines[I], 15, Length(Lines[I]) - 14);
    end;
  end;

  // 検出結果を表示する
  if BackendType = 'EDCB' then
  begin
    BackendResultLabel.Caption := 'EDCB を検出しました (' + EdcbUrl + ')';
    Result := True;
  end
  else if BackendType = 'Mirakurun' then
  begin
    BackendResultLabel.Caption := 'Mirakurun を検出しました (' + MirakurunUrl + ')';
    Result := True;
  end
  else
  begin
    BackendResultLabel.Caption := 'バックエンドを検出できませんでした。';
  end;
end;

// バックエンドの自動検出の経過秒数を表示するタイマー (1 秒ごとに呼び出される)
procedure DetectTimerProc(h: HWND; uMsg: UINT; idEvent: UINT_PTR; dwTime: DWORD);
begin
  DetectElapsedSeconds := DetectElapsedSeconds + 1;
  BackendResultLabel.Caption := '確認中...（' + IntToStr(DetectElapsedSeconds) + ' s）';
end;

// 「検出」ボタンが押されたときにバックエンドの自動検出を実行する
procedure DetectButtonClick(Sender: TObject);
var
  IP: String;
begin
  // 検出中の場合は何もしない (二重実行を防ぐ)
  if Detecting then Exit;

  // IP アドレスの入力チェック
  IP := Trim(IPEdit.Text);
  if IP = '' then
  begin
    MsgBox('IP アドレスを入力してください。', mbError, MB_OK);
    Exit;
  end;

  // 検出中状態にする (ボタンとナビゲーションを無効化して、二重実行やページ遷移・キャンセルを防ぐ)
  Detecting := True;
  BackendDetected := False;
  DetectElapsedSeconds := 0;
  DetectButton.Enabled := False;
  IPEdit.Enabled := False;
  WizardForm.BackButton.Enabled := False;
  WizardForm.NextButton.Enabled := False;
  WizardForm.CancelButton.Enabled := False;

  // 経過秒数を表示するタイマーを開始する
  BackendResultLabel.Caption := '確認中...（0 s）';
  DetectTimerID := SetTimer(0, 2, 1000, CreateCallback(@DetectTimerProc));

  // 検出に使用する IP アドレスを記録する (次へ時に IP が変更されていないか比較するため)
  DetectedIP := IP;

  // バックエンドの自動検出を実行する
  // (ewWaitUntilTerminated は実行中もメッセージを処理するため、タイマーによる経過秒数の表示が動作する)
  BackendDetected := DetectBackendFromIP(IP);

  // 経過秒数のタイマーを停止する
  if DetectTimerID <> 0 then
    KillTimer(0, DetectTimerID);

  // 検出できた場合は、検出されたバックエンドをラジオボタンに反映する
  if BackendDetected then
  begin
    if BackendType = 'EDCB' then
      EdcbRadio.Checked := True
    else if BackendType = 'Mirakurun' then
      MirakurunRadio.Checked := True;
  end;

  // 検出中状態を解除して、ボタンとナビゲーションを再度有効化する
  // 次へボタンはバックエンドの検出に成功した場合のみ有効化する (検出されていないと次へ進めない)
  Detecting := False;
  DetectButton.Enabled := True;
  IPEdit.Enabled := True;
  WizardForm.BackButton.Enabled := True;
  WizardForm.CancelButton.Enabled := True;
  if BackendDetected then
    WizardForm.NextButton.Enabled := True;
end;

// IP アドレスが変更されたら、それまでの検出結果を無効化する
// (検出結果は検出時点の IP アドレスに紐づくため、IP を変更した場合は再検出が必要になる)
procedure IPEditChange(Sender: TObject);
begin
  // 検出結果を無効化する
  BackendDetected := False;
  BackendType := '';
  EdcbUrl := '';
  MirakurunUrl := '';
  WizardForm.NextButton.Enabled := False;

  // 検出中でなければラベルも初期状態に戻す (検出中の経過秒数表示を上書きしないため)
  if not Detecting then
    BackendResultLabel.Caption := 'IP アドレスを入力して「検出」を押してください。';
end;

// エンコーダーの自動検出を実行する (既定の選択と利用可否を設定する)
procedure DetectEncoder;
var
  OutputFile: String;
  Lines: TArrayOfString;
  I: Integer;
  Key, Value: String;
begin
  if EncoderDetected then Exit;
  EncoderDetected := True;

  OutputFile := GetTempFilePath('konomitv-encoder-detect.txt');
  DeleteFile(OutputFile);

  // エンジンの --detect-encoder モードで検出する
  // 失敗した場合は EncoderDetected をリセットし、ページに再び入ったときに再検出できるようにする
  if RunEngine('--detect-encoder --output-file "' + OutputFile + '"', True) <> 0 then
  begin
    EncoderDetected := False;
    // 検出中に表示していた「エンコーダーを自動検出しています…」の状態から、失敗した旨の表示に戻す
    EncoderDescriptionLabel.Caption := 'エンコーダーの自動検出に失敗しました。';
    Exit;
  end;

  // 検出結果 (key=value) を読み込んでラジオボタンに反映する
  // (エンジンは UTF-8 で書き出すが、LoadStringsFromFile は BOM なし UTF-8 にも対応している)
  if LoadStringsFromFile(OutputFile, Lines) then
  begin
    for I := 0 to GetArrayLength(Lines) - 1 do
    begin
      Key := '';
      Value := '';
      if Pos('=', Lines[I]) > 0 then
      begin
        Key := Copy(Lines[I], 1, Pos('=', Lines[I]) - 1);
        Value := Copy(Lines[I], Pos('=', Lines[I]) + 1, Length(Lines[I]) - Pos('=', Lines[I]));
      end;

      // 既定のエンコーダーを設定する
      if Key = 'default' then
        EncoderType := Value
      // 接続されている GPU 名を取得する (説明ラベルに表示する)
      else if Key = 'gpu_names' then
        GpuNames := Value
      // 各エンコーダーの利用可否 (1: 利用可 / 0: 利用不可) に応じてラジオボタンを無効化する
      else if Key = 'qsvencc_available' then
        QsvenccRadio.Enabled := (Value = '1')
      else if Key = 'nvencc_available' then
        NvenccRadio.Enabled := (Value = '1')
      else if Key = 'vceencc_available' then
        VceenccRadio.Enabled := (Value = '1');
    end;
  end;

  // 検出された推奨エンコーダーを選択する
  if EncoderType = 'QSVEncC' then QsvenccRadio.Checked := True
  else if EncoderType = 'NVEncC' then NvenccRadio.Checked := True
  else if EncoderType = 'VCEEncC' then VceenccRadio.Checked := True
  else FfmpegRadio.Checked := True;

  // 検出結果を説明ラベルに表示する
  // GPU 名が検出できた場合は「推奨: エンコーダー名 (GPU: GPU名)」の形式で表示する
  if GpuNames <> '' then
    EncoderDescriptionLabel.Caption := 'お使いの PC に最適なエンコーダーを自動検出しました。' + #13#10 +
      '推奨: ' + EncoderType + ' (GPU: ' + GpuNames + ')'
  else
    EncoderDescriptionLabel.Caption := 'お使いの PC に最適なエンコーダーを自動検出しました。' + #13#10 +
      '推奨: ' + EncoderType;
end;

// ---------------------------------------------------------------------------
// フォルダ設定ページのヘルパー関数
// ---------------------------------------------------------------------------

// 指定されたパスが絶対パスかどうかを判定する
// (ドライブレター付きのパス (C:\...) または UNC パス (\\server\share\...) の場合のみ絶対パスとみなす)
function IsAbsolutePath(const Path: String): Boolean;
begin
  Result := False;
  // ドライブレター付きのパス (C:\ または C:/) を判定する
  if Length(Path) >= 3 then
    Result := (Path[2] = ':') and ((Path[3] = '\') or (Path[3] = '/'));
  // UNC パス (\\server\share\...) を判定する
  if (not Result) and (Length(Path) >= 2) then
    Result := (Path[1] = '\') and (Path[2] = '\');
end;

// リストボックスの内容から '|' 区切りのフォルダリスト文字列を再構築する
procedure RebuildFoldersString(const ListBox: TNewListBox; var Folders: String);
var
  I: Integer;
begin
  Folders := '';
  for I := 0 to ListBox.Items.Count - 1 do
    Folders := Folders + ListBox.Items[I] + '|';
end;

// 編集ボックスに入力されたフォルダパスを検証し、リストに追加する
// 戻り値: 追加に成功したかどうか
function AddFolderToList(const Edit: TNewEdit; const ListBox: TNewListBox; var Folders: String): Boolean;
var
  FolderPath: String;
begin
  Result := False;
  FolderPath := Trim(Edit.Text);

  // パスが入力されていない場合は何もしない
  if FolderPath = '' then Exit;

  // 絶対パスかどうかをチェックする (相対パスは設定できない)
  if not IsAbsolutePath(FolderPath) then
  begin
    MsgBox('フォルダパスは絶対パスで入力してください。', mbError, MB_OK);
    Exit;
  end;

  // フォルダが存在するかチェックする (存在しないフォルダは設定できない)
  if not DirExists(FolderPath) then
  begin
    MsgBox('指定されたフォルダが存在しません。', mbError, MB_OK);
    Exit;
  end;

  // 重複チェック (既に追加済みのフォルダは追加しない)
  if ListBox.Items.IndexOf(FolderPath) >= 0 then
  begin
    MsgBox('指定されたフォルダは既に追加されています。', mbInformation, MB_OK);
    Exit;
  end;

  // リストに追加して、'|' 区切りのフォルダリスト文字列を再構築する
  ListBox.Items.Add(FolderPath);
  RebuildFoldersString(ListBox, Folders);
  Edit.Text := '';

  Result := True;
end;

// リストボックスで選択されているフォルダを削除する
procedure RemoveSelectedFolder(const ListBox: TNewListBox; var Folders: String);
var
  Index: Integer;
begin
  // 何も選択されていない場合は何もしない
  Index := ListBox.ItemIndex;
  if Index < 0 then Exit;

  // 選択中のフォルダを削除して、'|' 区切りのフォルダリスト文字列を再構築する
  ListBox.Items.Delete(Index);
  RebuildFoldersString(ListBox, Folders);

  // 削除後に前後の項目を選択状態にする (連続削除をしやすくするため)
  // (末尾の項目を削除した場合は最後の項目を選択する)
  if ListBox.Items.Count > 0 then
  begin
    if Index >= ListBox.Items.Count then
      ListBox.ItemIndex := ListBox.Items.Count - 1
    else
      ListBox.ItemIndex := Index;
  end;
end;

// フォルダ選択ダイアログを開き、選択されたフォルダを編集ボックスに入力する
procedure BrowseFolder(const Edit: TNewEdit);
var
  FolderPath: String;
begin
  FolderPath := Edit.Text;
  if BrowseForFolder('フォルダを選択してください。', FolderPath, False) then
    Edit.Text := FolderPath;
end;

// フォルダ設定ページで「次へ」ボタンを押せるかどうかを更新する
// (録画フォルダとキャプチャフォルダの両方が1つ以上指定されている場合のみ進める)
procedure UpdateFolderPageNextButton;
begin
  WizardForm.NextButton.Enabled := (RecordedFolderListBox.Items.Count > 0) and (CaptureFolderListBox.Items.Count > 0);
end;

// 「参照...」ボタンが押されたときにフォルダ選択ダイアログを開く (録画フォルダ)
procedure RecordedFolderBrowseButtonClick(Sender: TObject);
begin
  BrowseFolder(RecordedFolderEdit);
end;

// 「追加」ボタンが押されたときに録画フォルダをリストに追加する
procedure RecordedFolderAddButtonClick(Sender: TObject);
begin
  if AddFolderToList(RecordedFolderEdit, RecordedFolderListBox, RecordedFolders) then
    UpdateFolderPageNextButton;
end;

// 「削除」ボタンが押されたときに選択中の録画フォルダを削除する
procedure RecordedFolderRemoveButtonClick(Sender: TObject);
begin
  RemoveSelectedFolder(RecordedFolderListBox, RecordedFolders);
  UpdateFolderPageNextButton;
end;

// 「参照...」ボタンが押されたときにフォルダ選択ダイアログを開く (キャプチャフォルダ)
procedure CaptureFolderBrowseButtonClick(Sender: TObject);
begin
  BrowseFolder(CaptureFolderEdit);
end;

// 「追加」ボタンが押されたときにキャプチャフォルダをリストに追加する
procedure CaptureFolderAddButtonClick(Sender: TObject);
begin
  if AddFolderToList(CaptureFolderEdit, CaptureFolderListBox, CaptureFolders) then
    UpdateFolderPageNextButton;
end;

// 「削除」ボタンが押されたときに選択中のキャプチャフォルダを削除する
procedure CaptureFolderRemoveButtonClick(Sender: TObject);
begin
  RemoveSelectedFolder(CaptureFolderListBox, CaptureFolders);
  UpdateFolderPageNextButton;
end;

// 進捗ファイルを読み込んで UI に反映する
// 戻り値: 完了 (True) / エラー (True) が検出されたかどうか (Done と Error に反映される)
procedure ReadProgressFile(const FileName: String; var Done: Boolean; var Error: Boolean; var ErrorMessage: String);
var
  Lines: TArrayOfString;
  I: Integer;
  Line: String;
  ProgressPercentStr: String;  // 進捗率 (小数点以下の桁を切り捨てた整数)
  DotPos: Integer;             // 進捗率文字列中の小数点の位置
begin
  Done := False;
  Error := False;
  ErrorMessage := '';
  if not FileExists(FileName) then Exit;

  // 進捗ファイルを読み込む (エンジンは UTF-8 で書き出すが、LoadStringsFromFile は BOM なし UTF-8 にも対応している)
  if LoadStringsFromFile(FileName, Lines) then
  begin
    // 前回の読み込み以降に追加された行のみをメモに追記する
    for I := LastProgressLineCount to GetArrayLength(Lines) - 1 do
    begin
      Line := Trim(Lines[I]);

      // 進捗率はメモに追記せず、プログレスバーとステータスラベルのみ更新する
      // (各プレフィックスは末尾のスペースを含むため、値はプレフィックス全体の後ろから始まる)
      if Copy(Line, 1, 11) = '[PROGRESS] ' then
      begin
        // 進捗率は小数点を含む小数 (例: 23.4) で書き出されるため、小数点以下の桁を切り捨てて整数として読み取る
        // (StrToIntDef をそのまま使うと小数点を含む文字列を整数として解析できず、常に 0 になってしまう)
        ProgressPercentStr := Copy(Line, 12, Length(Line) - 11);
        DotPos := Pos('.', ProgressPercentStr);
        if DotPos > 0 then
          ProgressPercentStr := Copy(ProgressPercentStr, 1, DotPos - 1);
        WizardForm.ProgressGauge.Position := StrToIntDef(ProgressPercentStr, 0);
      end
      else
      begin
        ProgressMemo.Lines.Add(Line);

        if Copy(Line, 1, 7) = '[STEP] ' then
          ProgressStatusLabel.Caption := Copy(Line, 8, Length(Line) - 7)
        else if Line = '[DONE]' then
        begin
          Done := True;
          ProgressStatusLabel.Caption := 'インストールが完了しました。';
        end
        else if Copy(Line, 1, 8) = '[ERROR] ' then
        begin
          Error := True;
          ErrorMessage := Copy(Line, 9, Length(Line) - 8);
          ProgressStatusLabel.Caption := 'エラーが発生しました。';
        end;
      end;
    end;
    LastProgressLineCount := GetArrayLength(Lines);
  end;
end;

// インストール進捗のポーリングタイマー (250ms ごとに呼び出され、進捗ファイルを読み込んで UI を更新する)
procedure InstallProgressTimerProc(h: HWND; uMsg: UINT; idEvent: UINT_PTR; dwTime: DWORD);
var
  Done, Error: Boolean;
  ErrorMessage: String;
begin
  // 完了を検出済みの場合は何もしない
  if InstallFinished then Exit;

  // 進捗ファイルを読み込んで UI に反映する
  ReadProgressFile(ProgressFilePath, Done, Error, ErrorMessage);

  // 完了 (DONE) またはエラー (ERROR) を検出したらタイマーを停止する
  if Done or Error then
  begin
    InstallFinished := True;
    if Error then
      InstallErrorMessage := ErrorMessage;
    if InstallProgressTimerID <> 0 then
      KillTimer(0, InstallProgressTimerID);
  end;
end;

// エンジンを無人モードで実行し、進捗ファイルのポーリングタイマーで UI を更新する
// 戻り値: インストールに成功したかどうか
function RunEngineAndWaitForInstall: Boolean;
var
  SettingsFile, Args: String;
  SettingsLines: TArrayOfString;
  ResultCode: Integer;
begin
  Result := False;

  // 設定ファイルを書き出す (エンジンがこのファイルを読み込んでインストールを実行する)
  // パスワードに日本語などの非 ASCII 文字が含まれていても正しく渡せるよう、UTF-8 で書き出す
  SettingsFile := GetTempFilePath('konomitv-settings.txt');
  // 進捗ファイルは {tmp} ではなく %TEMP% に置く
  // ({tmp} は Inno Setup 7 以降、保護された一時フォルダとして作成され、
  //  エンジン (別プロセス) からの書き込みが拒否されてしまうため)
  ProgressFilePath := AddBackslash(ExpandConstant('{%TEMP}')) + 'konomitv-install-progress.txt';
  DeleteFile(SettingsFile);
  DeleteFile(ProgressFilePath);
  SetArrayLength(SettingsLines, 9);
  SettingsLines[0] := 'install_path=' + WizardDirValue;
  SettingsLines[1] := 'backend=' + BackendType;
  SettingsLines[2] := 'edcb_url=' + EdcbUrl;
  SettingsLines[3] := 'mirakurun_url=' + MirakurunUrl;
  SettingsLines[4] := 'encoder=' + EncoderType;
  // 録画フォルダ・キャプチャフォルダ (ウィザードで追加した '|' 区切りのリスト)
  SettingsLines[5] := 'recorded_folders=' + RecordedFolders;
  SettingsLines[6] := 'capture_upload_folders=' + CaptureFolders;
  SettingsLines[7] := 'service_username=' + ServicePage.Values[0];
  SettingsLines[8] := 'service_password=' + ServicePage.Values[1];
  SaveStringsToUTF8FileWithoutBOM(SettingsFile, SettingsLines, False);

  // 進捗ファイルのポーリングタイマーを開始する (CreateCallback でコールバックを登録する)
  InstallFinished := False;
  InstallErrorMessage := '';
  LastProgressLineCount := 0;
  InstallProgressTimerID := SetTimer(0, 1, 250, CreateCallback(@InstallProgressTimerProc));

  // エンジンを無人モードで実行する
  // ewWaitUntilTerminated は実行中もメッセージを処理するため、タイマーによる進捗更新が動作する
  Args := '--install --settings-file "' + SettingsFile + '" --progress-file "' + ProgressFilePath + '"';
  ResultCode := RunEngine(Args, True);

  // 設定ファイルにはパスワードが含まれるため、成功・失敗にかかわらずすぐに削除する
  DeleteFile(SettingsFile);

  // ポーリングタイマーを停止する
  if InstallProgressTimerID <> 0 then
    KillTimer(0, InstallProgressTimerID);

  // エンジンの終了コードで結果を判定する (0: 成功 / 1: 失敗)
  if ResultCode = 0 then
    Result := True
  // エラー内容はタイマーが検出して InstallErrorMessage に格納済み
  else if InstallErrorMessage <> '' then
    MsgBox('インストールに失敗しました。' + #13#10 + #13#10 + InstallErrorMessage, mbError, MB_OK);
  // エンジンが起動できなかった場合 (エンジンが存在しない等) は、RunEngine がエラーメッセージを表示済みのため何もしない
end;

// ---------------------------------------------------------------------------
// ウィザードの初期化
// ---------------------------------------------------------------------------

procedure InitializeWizard;
begin
  // インストールエンジンを一時フォルダに展開する (ウィザード中の自動検出で使用する)
  ExtractTemporaryFile('{#MyEngineFileName}');

  // ----- インストール進捗の表示 (標準のインストールページに進捗表示を追加する) -----
  // インストールエンジンの進捗 (現在の処理とログ) を表示するためのラベルとログ表示を追加する
  // 進捗率は標準のプログレスバー (WizardForm.ProgressGauge) を再利用して表示する
  // (プログレスバーの範囲 (Max / Position) はファイルコピー段階の処理が完了した後の
  //   ssPostInstall で改めて設定するため、ここでは設定しない)

  // 標準のステータスラベル (「インストール実行中です…」など) とファイル名ラベルは、
  // エンジンの進捗表示 (現在の処理ラベルとログ表示) と重複するため非表示にする
  WizardForm.StatusLabel.Visible := False;
  WizardForm.FilenameLabel.Visible := False;

  ProgressStatusLabel := TNewStaticText.Create(WizardForm);
  ProgressStatusLabel.Parent := WizardForm.InstallingPage;
  ProgressStatusLabel.Left := ScaleX(8);
  ProgressStatusLabel.Top := ScaleY(0);
  ProgressStatusLabel.Width := WizardForm.InstallingPage.Width - ScaleX(16);
  ProgressStatusLabel.AutoSize := True;
  ProgressStatusLabel.Caption := 'インストールを開始します…';

  // 標準のプログレスバーはインストールページのログ表示の背後に固定配置されているため、
  // そのままだとログの隙間から緑色のバーが見えて意図が伝わりにくい。
  // ステータスラベルの直下に移動し、「現在の処理 → 進捗率 → ログ」の順で一続きに見えるようにする
  WizardForm.ProgressGauge.Left := ScaleX(8);
  WizardForm.ProgressGauge.Top := ProgressStatusLabel.Top + ProgressStatusLabel.Height + ScaleY(6);
  WizardForm.ProgressGauge.Width := WizardForm.InstallingPage.Width - ScaleX(16);
  WizardForm.ProgressGauge.Height := ScaleY(21);

  // ログ表示 (進捗ファイルの内容) はプログレスバーの下に配置し、ページの下端まで広げる
  ProgressMemo := TNewMemo.Create(WizardForm);
  ProgressMemo.Parent := WizardForm.InstallingPage;
  ProgressMemo.Left := ScaleX(8);
  ProgressMemo.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(8);
  ProgressMemo.Width := WizardForm.InstallingPage.Width - ScaleX(16);
  ProgressMemo.Height := WizardForm.InstallingPage.Height - ProgressMemo.Top - ScaleY(8);
  ProgressMemo.ReadOnly := True;
  ProgressMemo.ScrollBars := ssVertical;

  // ----- バックエンド設定ページ -----
  BackendPage := CreateCustomPage(wpSelectDir, 'バックエンドの設定', '利用するバックエンド (EDCB / Mirakurun) を設定します。');

  // IP アドレスの入力欄
  IPLabel := TNewStaticText.Create(BackendPage);
  IPLabel.Parent := BackendPage.Surface;
  IPLabel.Left := ScaleX(8);
  IPLabel.Top := ScaleY(0);
  IPLabel.Width := BackendPage.SurfaceWidth - ScaleX(16);
  IPLabel.AutoSize := True;
  IPLabel.Caption := 'バックエンドの IP アドレス (既定: 127.0.0.1)';

  IPEdit := TNewEdit.Create(BackendPage);
  IPEdit.Parent := BackendPage.Surface;
  IPEdit.Left := ScaleX(8);
  IPEdit.Top := ScaleY(24);
  IPEdit.Width := ScaleX(200);
  IPEdit.Text := '127.0.0.1';
  // IP アドレスが変更されたら検出結果を無効化する (初期値の設定後に OnChange を割り当てる)
  IPEdit.OnChange := @IPEditChange;

  // バックエンドの自動検出を実行するボタン
  DetectButton := TNewButton.Create(BackendPage);
  DetectButton.Parent := BackendPage.Surface;
  DetectButton.Left := ScaleX(216);
  DetectButton.Top := ScaleY(24);
  DetectButton.Width := ScaleX(90);
  DetectButton.Height := ScaleY(23);
  DetectButton.Caption := '検出';
  DetectButton.OnClick := @DetectButtonClick;

  // バックエンドの手動選択 (自動検出に成功した場合は、検出されたバックエンドが自動的に選択される)
  EdcbRadio := TNewRadioButton.Create(BackendPage);
  EdcbRadio.Parent := BackendPage.Surface;
  EdcbRadio.Left := ScaleX(8);
  EdcbRadio.Top := ScaleY(56);
  EdcbRadio.Width := BackendPage.SurfaceWidth - ScaleX(16);
  EdcbRadio.Caption := 'EDCB';
  EdcbRadio.Checked := True;

  MirakurunRadio := TNewRadioButton.Create(BackendPage);
  MirakurunRadio.Parent := BackendPage.Surface;
  MirakurunRadio.Left := ScaleX(8);
  MirakurunRadio.Top := ScaleY(80);
  MirakurunRadio.Width := BackendPage.SurfaceWidth - ScaleX(16);
  MirakurunRadio.Caption := 'Mirakurun';

  // 自動検出の結果を表示するラベル
  BackendResultLabel := TNewStaticText.Create(BackendPage);
  BackendResultLabel.Parent := BackendPage.Surface;
  BackendResultLabel.Left := ScaleX(8);
  BackendResultLabel.Top := ScaleY(104);
  BackendResultLabel.Width := BackendPage.SurfaceWidth - ScaleX(16);
  BackendResultLabel.AutoSize := True;
  BackendResultLabel.Caption := 'IP アドレスを入力して「検出」を押してください。';

  // ----- エンコーダー設定ページ -----
  EncoderPage := CreateCustomPage(BackendPage.ID, 'エンコーダーの設定', '利用するエンコーダーを設定します。');
  EncoderDescriptionLabel := TNewStaticText.Create(EncoderPage);
  EncoderDescriptionLabel.Parent := EncoderPage.Surface;
  EncoderDescriptionLabel.Left := ScaleX(8);
  EncoderDescriptionLabel.Top := ScaleY(0);
  EncoderDescriptionLabel.Width := EncoderPage.SurfaceWidth - ScaleX(16);
  EncoderDescriptionLabel.AutoSize := True;
  EncoderDescriptionLabel.Caption := 'エンコーダーを自動検出しています…';

  FfmpegRadio := TNewRadioButton.Create(EncoderPage);
  FfmpegRadio.Parent := EncoderPage.Surface;
  FfmpegRadio.Left := ScaleX(8);
  FfmpegRadio.Top := ScaleY(56);
  FfmpegRadio.Width := EncoderPage.SurfaceWidth - ScaleX(16);
  FfmpegRadio.Caption := 'FFmpeg (ソフトウェアエンコーダー)';
  FfmpegRadio.Checked := True;

  QsvenccRadio := TNewRadioButton.Create(EncoderPage);
  QsvenccRadio.Parent := EncoderPage.Surface;
  QsvenccRadio.Left := ScaleX(8);
  QsvenccRadio.Top := ScaleY(80);
  QsvenccRadio.Width := EncoderPage.SurfaceWidth - ScaleX(16);
  QsvenccRadio.Caption := 'QSVEncC (Intel QSV)';

  NvenccRadio := TNewRadioButton.Create(EncoderPage);
  NvenccRadio.Parent := EncoderPage.Surface;
  NvenccRadio.Left := ScaleX(8);
  NvenccRadio.Top := ScaleY(104);
  NvenccRadio.Width := EncoderPage.SurfaceWidth - ScaleX(16);
  NvenccRadio.Caption := 'NVEncC (NVIDIA NVENC)';

  VceenccRadio := TNewRadioButton.Create(EncoderPage);
  VceenccRadio.Parent := EncoderPage.Surface;
  VceenccRadio.Left := ScaleX(8);
  VceenccRadio.Top := ScaleY(128);
  VceenccRadio.Width := EncoderPage.SurfaceWidth - ScaleX(16);
  VceenccRadio.Caption := 'VCEEncC (AMD VCE)';

  // エンコーダーの自動検出を実行する (初回のページ表示時に CurPageChanged で実行される)
  EncoderDetected := False;

  // ----- フォルダ設定ページ -----
  // 録画フォルダとキャプチャフォルダを設定する (どちらも最低1つは指定する必要がある)
  FolderPage := CreateCustomPage(EncoderPage.ID, 'フォルダの設定', '録画フォルダとキャプチャフォルダを設定します。');

  // 録画フォルダセクション
  RecordedFoldersLabel := TNewStaticText.Create(FolderPage);
  RecordedFoldersLabel.Parent := FolderPage.Surface;
  RecordedFoldersLabel.Left := ScaleX(8);
  RecordedFoldersLabel.Top := ScaleY(0);
  RecordedFoldersLabel.Width := FolderPage.SurfaceWidth - ScaleX(16);
  RecordedFoldersLabel.AutoSize := True;
  RecordedFoldersLabel.Caption := '録画フォルダ (必須)';

  RecordedFolderEdit := TNewEdit.Create(FolderPage);
  RecordedFolderEdit.Parent := FolderPage.Surface;
  RecordedFolderEdit.Left := ScaleX(8);
  RecordedFolderEdit.Top := ScaleY(20);
  RecordedFolderEdit.Width := ScaleX(176);

  RecordedFolderBrowseButton := TNewButton.Create(FolderPage);
  RecordedFolderBrowseButton.Parent := FolderPage.Surface;
  RecordedFolderBrowseButton.Left := ScaleX(192);
  RecordedFolderBrowseButton.Top := ScaleY(20);
  RecordedFolderBrowseButton.Width := ScaleX(72);
  RecordedFolderBrowseButton.Height := ScaleY(23);
  RecordedFolderBrowseButton.Caption := '参照...';
  RecordedFolderBrowseButton.OnClick := @RecordedFolderBrowseButtonClick;

  RecordedFolderAddButton := TNewButton.Create(FolderPage);
  RecordedFolderAddButton.Parent := FolderPage.Surface;
  RecordedFolderAddButton.Left := ScaleX(272);
  RecordedFolderAddButton.Top := ScaleY(20);
  RecordedFolderAddButton.Width := ScaleX(56);
  RecordedFolderAddButton.Height := ScaleY(23);
  RecordedFolderAddButton.Caption := '追加';
  RecordedFolderAddButton.OnClick := @RecordedFolderAddButtonClick;

  RecordedFolderListBox := TNewListBox.Create(FolderPage);
  RecordedFolderListBox.Parent := FolderPage.Surface;
  RecordedFolderListBox.Left := ScaleX(8);
  RecordedFolderListBox.Top := ScaleY(48);
  RecordedFolderListBox.Width := FolderPage.SurfaceWidth - ScaleX(16);
  RecordedFolderListBox.Height := ScaleY(70);

  RecordedFolderRemoveButton := TNewButton.Create(FolderPage);
  RecordedFolderRemoveButton.Parent := FolderPage.Surface;
  RecordedFolderRemoveButton.Left := FolderPage.SurfaceWidth - ScaleX(64);
  RecordedFolderRemoveButton.Top := ScaleY(122);
  RecordedFolderRemoveButton.Width := ScaleX(56);
  RecordedFolderRemoveButton.Height := ScaleY(23);
  RecordedFolderRemoveButton.Caption := '削除';
  RecordedFolderRemoveButton.OnClick := @RecordedFolderRemoveButtonClick;

  // キャプチャフォルダセクション
  CaptureFoldersLabel := TNewStaticText.Create(FolderPage);
  CaptureFoldersLabel.Parent := FolderPage.Surface;
  CaptureFoldersLabel.Left := ScaleX(8);
  CaptureFoldersLabel.Top := ScaleY(152);
  CaptureFoldersLabel.Width := FolderPage.SurfaceWidth - ScaleX(16);
  CaptureFoldersLabel.AutoSize := True;
  CaptureFoldersLabel.Caption := 'キャプチャフォルダ (必須)';

  CaptureFolderEdit := TNewEdit.Create(FolderPage);
  CaptureFolderEdit.Parent := FolderPage.Surface;
  CaptureFolderEdit.Left := ScaleX(8);
  CaptureFolderEdit.Top := ScaleY(172);
  CaptureFolderEdit.Width := ScaleX(176);

  CaptureFolderBrowseButton := TNewButton.Create(FolderPage);
  CaptureFolderBrowseButton.Parent := FolderPage.Surface;
  CaptureFolderBrowseButton.Left := ScaleX(192);
  CaptureFolderBrowseButton.Top := ScaleY(172);
  CaptureFolderBrowseButton.Width := ScaleX(72);
  CaptureFolderBrowseButton.Height := ScaleY(23);
  CaptureFolderBrowseButton.Caption := '参照...';
  CaptureFolderBrowseButton.OnClick := @CaptureFolderBrowseButtonClick;

  CaptureFolderAddButton := TNewButton.Create(FolderPage);
  CaptureFolderAddButton.Parent := FolderPage.Surface;
  CaptureFolderAddButton.Left := ScaleX(272);
  CaptureFolderAddButton.Top := ScaleY(172);
  CaptureFolderAddButton.Width := ScaleX(56);
  CaptureFolderAddButton.Height := ScaleY(23);
  CaptureFolderAddButton.Caption := '追加';
  CaptureFolderAddButton.OnClick := @CaptureFolderAddButtonClick;

  CaptureFolderListBox := TNewListBox.Create(FolderPage);
  CaptureFolderListBox.Parent := FolderPage.Surface;
  CaptureFolderListBox.Left := ScaleX(8);
  CaptureFolderListBox.Top := ScaleY(200);
  CaptureFolderListBox.Width := FolderPage.SurfaceWidth - ScaleX(16);
  CaptureFolderListBox.Height := ScaleY(70);

  CaptureFolderRemoveButton := TNewButton.Create(FolderPage);
  CaptureFolderRemoveButton.Parent := FolderPage.Surface;
  CaptureFolderRemoveButton.Left := FolderPage.SurfaceWidth - ScaleX(64);
  CaptureFolderRemoveButton.Top := ScaleY(274);
  CaptureFolderRemoveButton.Width := ScaleX(56);
  CaptureFolderRemoveButton.Height := ScaleY(23);
  CaptureFolderRemoveButton.Caption := '削除';
  CaptureFolderRemoveButton.OnClick := @CaptureFolderRemoveButtonClick;

  // ----- サービスアカウント設定ページ -----
  ServicePage := CreateInputQueryPage(FolderPage.ID, 'サービスのアカウント設定', 'KonomiTV サービスを実行するユーザーを設定します。',
    'KonomiTV は Windows サービスとしてバックグラウンドで動作します。' + #13#10 +
    'サービスの実行ユーザー名とパスワードを入力してください。' + #13#10 +
    '入力されたパスワードはサービスの登録にのみ使用され、それ以外の用途には使用されません。');
  ServicePage.Add('ユーザー名:', False);
  ServicePage.Add('パスワード:', True);
  // 既定では現在ログオン中のユーザーを使用する
  ServicePage.Values[0] := ExpandConstant('{%USERNAME}');
end;

// ---------------------------------------------------------------------------
// ページ遷移時の処理
// ---------------------------------------------------------------------------

// ページが切り替わったときの処理
procedure CurPageChanged(CurPageID: Integer);
begin
  // バックエンド設定ページでは、バックエンドが検出されるまで次へ進めないようにする
  if CurPageID = BackendPage.ID then
  begin
    if not BackendDetected then
      WizardForm.NextButton.Enabled := False;
  end
  // エンコーダー設定ページに初めて入ったときに、エンコーダーの自動検出を実行する
  else if CurPageID = EncoderPage.ID then
    DetectEncoder
  // フォルダ設定ページでは、録画フォルダとキャプチャフォルダの両方が指定されるまで次へ進めない
  else if CurPageID = FolderPage.ID then
    UpdateFolderPageNextButton;
end;

// ---------------------------------------------------------------------------
// ページ遷移時の処理
// ---------------------------------------------------------------------------

// バックエンド設定ページから次へ進むときに、選択されたバックエンドを確定する
function NextButtonClick(CurPageID: Integer): Boolean;
var
  IP: String;
begin
  Result := True;

  if CurPageID = BackendPage.ID then
  begin
    // 検出中はページを進めない (防御的なチェック。通常はナビゲーションボタンが無効化されている)
    if Detecting then
    begin
      Result := False;
      Exit;
    end;

    // バックエンドが検出されていない場合は次へ進めない
    // (通常は Next ボタンが無効化されているが、防御的にチェックする)
    if not BackendDetected then
    begin
      MsgBox('バックエンドを検出してください。' + #13#10 + #13#10 +
        'IP アドレスを確認して「検出」を押してください。', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    IP := Trim(IPEdit.Text);
    if IP = '' then
    begin
      MsgBox('IP アドレスを入力してください。', mbError, MB_OK);
      Result := False;
      Exit;
    end;

    // ラジオボタンで選択されたバックエンドを確定する
    // (自動検出に成功している場合は検出された URL を優先して使い、未検出の場合は IP アドレスから URL を組み立てる)
    // 検出済みの URL は、検出時と同じ IP アドレスの場合のみ使用する (検出後に IP を変更した場合は再構築する)
    if EdcbRadio.Checked then
    begin
      BackendType := 'EDCB';
      if (EdcbUrl = '') or (DetectedIP <> IP) then
        EdcbUrl := 'tcp://' + IP + ':4510/';
      MirakurunUrl := '';
    end
    else
    begin
      BackendType := 'Mirakurun';
      if (MirakurunUrl = '') or (DetectedIP <> IP) then
        MirakurunUrl := 'http://' + IP + ':40772/';
      EdcbUrl := '';
    end;
  end
  else if CurPageID = EncoderPage.ID then
  begin
    // 選択されたエンコーダーを確定する
    if QsvenccRadio.Checked then EncoderType := 'QSVEncC'
    else if NvenccRadio.Checked then EncoderType := 'NVEncC'
    else if VceenccRadio.Checked then EncoderType := 'VCEEncC'
    else EncoderType := 'FFmpeg';
  end
  else if CurPageID = FolderPage.ID then
  begin
    // 録画フォルダとキャプチャフォルダがそれぞれ1つ以上指定されているかチェックする
    // (通常は次へボタンが無効化されているが、防御的にチェックする)
    if RecordedFolderListBox.Items.Count = 0 then
    begin
      MsgBox('少なくとも1つの録画フォルダを指定してください。', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if CaptureFolderListBox.Items.Count = 0 then
    begin
      MsgBox('少なくとも1つのキャプチャフォルダを指定してください。', mbError, MB_OK);
      Result := False;
      Exit;
    end;
  end
  else if CurPageID = wpReady then
  begin
    // 既存の KonomiTV がインストールされている場合は、上書きの確認を必ず行う
    if IsExistingKonomiTV(WizardDirValue) then
    begin
      if MsgBox('このフォルダには既に KonomiTV がインストールされています。' + #13#10 + #13#10 +
        '上書きインストールしますか?' + #13#10 +
        '(既存の設定・データベース・録画データは保持されます)', mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
    end
    // 空ではないが KonomiTV ではないファイルが存在する場合は警告する
    else if DirExists(WizardDirValue) and (not IsDirEmpty(WizardDirValue)) then
    begin
      if MsgBox('インストール先のフォルダには KonomiTV 以外のファイルが存在します。' + #13#10 + #13#10 +
        'インストール先のフォルダは空にするか、別のフォルダを指定してください。' + #13#10 + #13#10 +
        'このままインストールを続行しますか?', mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
    end;
  end;
end;

// ---------------------------------------------------------------------------
// インストール処理
// ---------------------------------------------------------------------------

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // ファイルのコピーが完了したら、エンジンによるインストールを実行する
  // (進捗は標準のインストールページに追加したラベル・プログレスバー・ログに表示される)
  if CurStep = ssPostInstall then
  begin
    // ファイルコピー段階で Inno Setup が書き換えたプログレスバーの範囲を、進捗率 (0〜100%) 表示用に再初期化する
    // (ReadProgressFile が書き込む進捗率 (パーセント値) が正しいスケールで表示されるようにする)
    WizardForm.ProgressGauge.Max := 100;
    WizardForm.ProgressGauge.Position := 0;

    // エンジンを無人モードで実行して進捗を表示する
    // 失敗した場合はインストールを中断する
    if not RunEngineAndWaitForInstall then
      Abort();
  end;
end;

// ---------------------------------------------------------------------------
// アンインストール処理
// ---------------------------------------------------------------------------

// アンインストール時に Windows サービスとファイアウォール規則を削除する
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PythonPath, ServerDir: String;
  ResultCode: Integer;
begin
  // アンインストール処理の最初に、Windows サービスとファイアウォール規則を削除する
  if CurUninstallStep = usUninstall then
  begin
    ServerDir := AddBackslash(ExpandConstant('{app}')) + 'server';
    PythonPath := AddBackslash(ServerDir) + '.venv\Scripts\python.exe';

    // Windows サービスを終了・削除する (KonomiTV-Service.py は仮想環境の Python で直接実行する)
    if FileExists(PythonPath) then
    begin
      Exec(PythonPath, 'KonomiTV-Service.py stop', ServerDir, SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec(PythonPath, 'KonomiTV-Service.py uninstall', ServerDir, SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    // Windows Defender ファイアウォールの受信規則を削除する
    // (規則名 "KonomiTV Service" にスペースが含まれるため、名前全体を引用符で囲んで 1 つの引数として渡す)
    Exec('netsh', 'advfirewall firewall delete rule name="KonomiTV Service"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end
  // アンインストール処理の最後に、インストールエンジンが作成したファイルをすべて削除する
  // (KonomiTV のファイルは Inno Setup がインストールしたものではないため、明示的に削除する必要がある)
  else if CurUninstallStep = usPostUninstall then
  begin
    // インストール先のフォルダに KonomiTV 以外のファイルが存在する場合は、
    // 勝手にフォルダごと削除せず、ユーザーに確認を取る
    if HasForeignFiles(ExpandConstant('{app}')) then
    begin
      if MsgBox('インストール先のフォルダには KonomiTV 以外のファイルが存在します。' + #13#10 + #13#10 +
        'フォルダごと削除しますか?' + #13#10 +
        '(「はい」を選択するとフォルダ内のすべてのファイルが削除されます)', mbConfirmation, MB_YESNO) = IDYES then
        DelTree(ExpandConstant('{app}'), True, True, True);
    end
    // KonomiTV のファイルのみが存在する場合 (またはフォルダが空の場合) は、そのまま自動的に削除する
    else
      DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
