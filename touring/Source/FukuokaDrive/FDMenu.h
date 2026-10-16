#pragma once

#include "CoreMinimal.h"

class APlayerController;
class AFDTravelPoint;
class SWidget;
class UGameViewportClient;
class UWorld;

/**
 * 画面の左に出す選択メニュー (車体色・ファストトラベル・Tab の設定メニュー)。バイクと徒歩の両方で使う。
 * 開いているあいだはマウスのカーソルを出し、閉じるとゲームの操作に戻す。
 * 一度に開くメニューは 1 つだけ (別のメニューを開くと前のメニューは閉じる)。開いているメニューの上で Tab を押すと閉じる。
 */
class FFDMenu
{
public:
	/** メニューの1行。Swatch があれば色見本を出す */
	struct FItem
	{
		FString Label;
		TOptional<FLinearColor> Swatch;
		bool bCurrent = false;
		TFunction<void()> OnPick;
	};

	~FFDMenu() { Close(); }

	/** FocusIndex を指定すると、その行にカーソルを置いて開く (切り替えたあと同じ行で開き直すとき) */
	void Open(APlayerController* PC, const FString& Title, TArray<FItem> Items, const FString& Footer, int32 FocusIndex = INDEX_NONE);
	/** 好きな中身 (拡大マップなど) を画面いっぱいに出す。Focus はキー入力を受け取る部品 */
	void OpenWidget(APlayerController* PC, TSharedRef<SWidget> Content, TSharedPtr<SWidget> Focus);
	void Close();
	bool IsOpen() const { return Widget.IsValid(); }

	/** どれかのメニュー (地図を含む) が開いているか。開いている間はマウスで視点を回さない */
	static bool IsAnyOpen() { return Active != nullptr; }

	/** ファストトラベルの行き先を並べたメニューを開く。選ぶと Travel が呼ばれる */
	void OpenTravel(APlayerController* PC, TFunction<void(const AFDTravelPoint*)> Travel);

	/** レベルにある行き先を並び順で */
	static TArray<AFDTravelPoint*> GetTravelPoints(UWorld* World);

private:
	void Show(APlayerController* PC, TSharedRef<SWidget> Content, TSharedPtr<SWidget> Focus, int32 ZOrder);

	TSharedPtr<SWidget> Widget;
	TWeakObjectPtr<APlayerController> Owner;
	TWeakObjectPtr<UGameViewportClient> Viewport;

	static FFDMenu* Active;
};

/**
 * Tab のメニューで切り替える、どの乗り物でも共通の表示の設定。GameUserSettings.ini に残り、次に遊ぶときも同じになる。
 */
struct FFDSettings
{
	/** 右下のミニマップ */
	static bool ShowMinimap();
	static void SetShowMinimap(bool bShow);

	/** 画面左上の速度・時刻と操作の文字 */
	static bool ShowHelpText();
	static void SetShowHelpText(bool bShow);
};
