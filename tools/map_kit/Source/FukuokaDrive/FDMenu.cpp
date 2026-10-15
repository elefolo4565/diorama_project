#include "FDMenu.h"

#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "FDTravelPoint.h"
#include "GameFramework/PlayerController.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

void FFDMenu::Open(APlayerController* PC, const FString& Title, TArray<FItem> Items, const FString& Footer)
{
	Close();
	UGameViewportClient* GameViewport = PC && PC->GetWorld() ? PC->GetWorld()->GetGameViewport() : nullptr;
	if (!GameViewport)
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
	for (FItem& Item : Items)
	{
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
		if (Item.bCurrent || !Focus.IsValid())
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

	Widget = SNew(SBox).HAlign(HAlign_Left).VAlign(VAlign_Center).Padding(FMargin(48.f, 0.f))
	[
		SNew(SBorder).BorderImage(White).BorderBackgroundColor(FLinearColor(0.f, 0.f, 0.f, 0.65f)).Padding(18.f)
		[
			List
		]
	];
	Owner = PC;
	Viewport = GameViewport;
	GameViewport->AddViewportWidgetContent(Widget.ToSharedRef(), 10);

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
	const FString Footer = Items.Num() > 0 ? TEXT("F キーで閉じる")  // F キーで閉じる
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
