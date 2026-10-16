#include "FDMenu.h"

#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FDTravelPoint.h"
#include "GameFramework/PlayerController.h"
#include "Misc/ConfigCacheIni.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Text/STextBlock.h"

FFDMenu* FFDMenu::Active = nullptr;

namespace
{
	/** メニューのいちばん外側。中のボタンより先に Tab を受け取り、メニューを閉じる */
	class SFDMenuRoot : public SCompoundWidget
	{
	public:
		SLATE_BEGIN_ARGS(SFDMenuRoot) {}
			SLATE_DEFAULT_SLOT(FArguments, Content)
			SLATE_EVENT(FSimpleDelegate, OnClose)
		SLATE_END_ARGS()

		void Construct(const FArguments& InArgs)
		{
			OnClose = InArgs._OnClose;
			ChildSlot[InArgs._Content.Widget];
		}

		virtual FReply OnPreviewKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override
		{
			if (InKeyEvent.GetKey() == EKeys::Tab)
			{
				OnClose.ExecuteIfBound();
				return FReply::Handled();
			}
			return FReply::Unhandled();
		}

	private:
		FSimpleDelegate OnClose;
	};

	const TCHAR* const SettingsSection = TEXT("FukuokaDrive.Settings");

	/** 毎フレーム読むので、一度読んだ値を覚えておく */
	bool GetSetting(TOptional<bool>& Cache, const TCHAR* Key)
	{
		if (!Cache.IsSet())
		{
			bool bValue = true;
			GConfig->GetBool(SettingsSection, Key, bValue, GGameUserSettingsIni);
			Cache = bValue;
		}
		return Cache.GetValue();
	}

	void SetSetting(TOptional<bool>& Cache, const TCHAR* Key, bool bValue)
	{
		Cache = bValue;
		GConfig->SetBool(SettingsSection, Key, bValue, GGameUserSettingsIni);
		GConfig->Flush(false, GGameUserSettingsIni);
	}

	TOptional<bool> ShowMinimapCache;
	TOptional<bool> ShowHelpTextCache;
}

bool FFDSettings::ShowMinimap() { return GetSetting(ShowMinimapCache, TEXT("ShowMinimap")); }
void FFDSettings::SetShowMinimap(bool bShow) { SetSetting(ShowMinimapCache, TEXT("ShowMinimap"), bShow); }
bool FFDSettings::ShowHelpText() { return GetSetting(ShowHelpTextCache, TEXT("ShowHelpText")); }
void FFDSettings::SetShowHelpText(bool bShow) { SetSetting(ShowHelpTextCache, TEXT("ShowHelpText"), bShow); }

void FFDMenu::Open(APlayerController* PC, const FString& Title, TArray<FItem> Items, const FString& Footer, int32 FocusIndex)
{
	Close();
	if (!PC || !PC->GetWorld() || !PC->GetWorld()->GetGameViewport())
	{
		return;
	}

	const FSlateBrush* White = FCoreStyle::Get().GetBrush(TEXT("GenericWhiteBox"));
	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	List->AddSlot().AutoHeight().Padding(4.f, 0.f, 4.f, 10.f)
	[
		SNew(STextBlock)
		.Text(FText::FromString(Title))
		.Font(FCoreStyle::GetDefaultFontStyle("Bold", 22))
		.ColorAndOpacity(FLinearColor::White)
	];

	TSharedPtr<SWidget> Focus;
	for (int32 Index = 0; Index < Items.Num(); ++Index)
	{
		FItem& Item = Items[Index];
		TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox);
		if (Item.Swatch.IsSet())
		{
			Row->AddSlot().AutoWidth().VAlign(VAlign_Center).Padding(4.f)
			[
				SNew(SBox).WidthOverride(32.f).HeightOverride(32.f)
				[
					SNew(SImage).Image(White).ColorAndOpacity(FSlateColor(Item.Swatch.GetValue()))
				]
			];
		}
		Row->AddSlot().AutoWidth().VAlign(VAlign_Center).Padding(10.f, 4.f, 24.f, 4.f)
		[
			SNew(STextBlock)
			.Text(FText::FromString(Item.Label))
			.Font(FCoreStyle::GetDefaultFontStyle(Item.bCurrent ? "Bold" : "Regular", 18))
		];
		TSharedRef<SButton> Button = SNew(SButton)
			.OnClicked_Lambda([this, OnPick = MoveTemp(Item.OnPick)]()
			{
				// 閉じるとこのボタンも消えるので、選んだ処理を写してから閉じる
				const TFunction<void()> Pick = OnPick;
				Close();
				if (Pick)
				{
					Pick();
				}
				return FReply::Handled();
			})
			[
				Row
			];
		List->AddSlot().AutoHeight().Padding(0.f, 3.f)[Button];
		if (FocusIndex == INDEX_NONE ? (Item.bCurrent || !Focus.IsValid()) : (Index == FocusIndex || !Focus.IsValid()))
		{
			Focus = Button;
		}
	}
	List->AddSlot().AutoHeight().Padding(4.f, 10.f, 4.f, 0.f)
	[
		SNew(STextBlock)
		.Text(FText::FromString(Footer))
		.Font(FCoreStyle::GetDefaultFontStyle("Regular", 12))
		.ColorAndOpacity(FLinearColor(0.8f, 0.8f, 0.8f))
	];

	TSharedRef<SWidget> Content = SNew(SBox).HAlign(HAlign_Left).VAlign(VAlign_Center).Padding(FMargin(48.f, 0.f))
	[
		SNew(SBorder).BorderImage(White).BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, 0.65f)).Padding(18.f)
		[
			List
		]
	];
	Show(PC, Content, Focus, 10);
}

void FFDMenu::OpenWidget(APlayerController* PC, TSharedRef<SWidget> Content, TSharedPtr<SWidget> Focus)
{
	Close();
	Show(PC, Content, Focus, 9);
}

void FFDMenu::Show(APlayerController* PC, TSharedRef<SWidget> Content, TSharedPtr<SWidget> Focus, int32 ZOrder)
{
	UGameViewportClient* GameViewport = PC && PC->GetWorld() ? PC->GetWorld()->GetGameViewport() : nullptr;
	if (!GameViewport)
	{
		return;
	}
	// 一度に開くのは 1 つだけ (バイクのメニューと Tab のメニューが重ならないように)
	if (Active && Active != this)
	{
		Active->Close();
	}
	Widget = SNew(SFDMenuRoot).OnClose(FSimpleDelegate::CreateLambda([this]() { Close(); }))
	[
		Content
	];
	Active = this;
	Owner = PC;
	Viewport = GameViewport;
	GameViewport->AddViewportWidgetContent(Widget.ToSharedRef(), ZOrder);

	FInputModeGameAndUI Mode;
	Mode.SetWidgetToFocus(Focus);
	Mode.SetHideCursorDuringCapture(false);
	PC->SetInputMode(Mode);
	PC->SetShowMouseCursor(true);
}

void FFDMenu::Close()
{
	if (!Widget.IsValid())
	{
		return;
	}
	if (UGameViewportClient* GameViewport = Viewport.Get())
	{
		GameViewport->RemoveViewportWidgetContent(Widget.ToSharedRef());
	}
	Widget.Reset();
	if (Active == this)
	{
		Active = nullptr;
	}
	if (APlayerController* PC = Owner.Get())
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->SetShowMouseCursor(false);
	}
	Owner.Reset();
	Viewport.Reset();
}

void FFDMenu::OpenTravel(APlayerController* PC, TFunction<void(const AFDTravelPoint*)> Travel)
{
	TArray<FItem> Items;
	for (AFDTravelPoint* Point : GetTravelPoints(PC ? PC->GetWorld() : nullptr))
	{
		TWeakObjectPtr<AFDTravelPoint> Weak(Point);
		Items.Add({Point->DisplayName.IsEmpty() ? Point->GetName() : Point->DisplayName, TOptional<FLinearColor>(), false, [Travel, Weak]()
		{
			if (Weak.IsValid())
			{
				Travel(Weak.Get());
			}
		}});
	}
	const FString Footer = Items.Num() > 0 ? TEXT("F \u304b Tab \u30ad\u30fc\u3067\u9589\u3058\u308b")  // F か Tab キーで閉じる
	                                       // 行き先がありません (setup_project.py を実行してください)
	                                       : TEXT("行き先がありません (setup_project.py を実行してください)");
	Open(PC, TEXT("ファストトラベル"),  // ファストトラベル
	     MoveTemp(Items), Footer);
}

TArray<AFDTravelPoint*> FFDMenu::GetTravelPoints(UWorld* World)
{
	TArray<AFDTravelPoint*> Points;
	if (World)
	{
		for (TActorIterator<AFDTravelPoint> It(World); It; ++It)
		{
			Points.Add(*It);
		}
	}
	Points.Sort([](const AFDTravelPoint& A, const AFDTravelPoint& B)
	{
		return A.Order != B.Order ? A.Order < B.Order : A.DisplayName < B.DisplayName;
	});
	return Points;
}
