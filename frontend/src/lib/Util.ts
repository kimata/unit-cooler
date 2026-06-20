import dayjs from "dayjs";

export const dateText = (date: dayjs.Dayjs | null) => {
    if (date == null) {
        return "?";
    } else {
        return date.format("M月D日 HH:mm");
    }
};
